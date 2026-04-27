#!/usr/bin/env python3
"""
TradeMind - A-Stock Analysis Tool
Enhanced: 10+ strategies, parameter optimization, Monte Carlo,
multi-dimensional alerts (57 types), candlestick patterns.
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from skill import StockAnalysisSkill
from report import generate_report
from backtest import (
    BacktestEngine, run_backtest, format_backtest_result,
    optimize_backtest, monte_carlo_simulation, plot_equity_curve,
    STRATEGIES, CostModel
)
from data.price import get_price_data, get_latest_price
from analysis.technical import (
    get_trend_detail, get_indicator_summary,
    detect_candlestick_patterns, detect_price_anomaly
)
from predict import predict_price, format_prediction_report
from visualization import plotly_chart
from alerts import (
    AlertEngine, check_stock_alerts,
    apply_preset, PRESET_ALERTS, ALL_ALERT_TYPES, ALERT_CATEGORIES
)
from data.news import get_stock_news
from analysis.sentiment import analyze_news, get_sentiment_for_stock
from analysis.sentiment_llm import SentimentLearnedStore
from analysis.llm_advisor import analyze_report as llm_analyze


def print_usage():
    print("TradeMind - A-Stock Analysis Tool (Enhanced)")
    print("")
    print("Core Analysis:")
    print("  python main.py <symbol>              Analyze stock (e.g., 000001, 600519)")
    print("  python main.py --market              Market overview (all major indices)")
    print("  python main.py --sectors [N]         Top N sector ranking (default: 10)")
    print("  python main.py --report <symbol>     Full analysis report")
    print("")
    print("Backtesting (enhanced — 10 strategies + optimization):")
    print("  python main.py --backtest <sym>                 Run all strategies")
    print("  python main.py --backtest <sym> <strat>          Run specific strategy")
    print("  python main.py --backtest <sym> <strat> <capital>  With custom capital")
    print("  python main.py --bt-optimize <sym> <strat>      Parameter optimization")
    print("  python main.py --bt-monte <sym> <strat>          Monte Carlo (200 sims)")
    print("  python main.py --bt-chart <sym> <strat>          Equity curve chart (HTML)")
    print(f"  Strategies: {', '.join(STRATEGIES.keys())}")
    print("")
    print("Alerts (enhanced — 57 types, 5 presets):")
    print("  python main.py --alerts                       List configured alerts")
    print("  python main.py --alert-add <sym> <type> <thr> Add alert")
    print("  python main.py --alert-check <sym>             Full alert check")
    print("  python main.py --alert-preset <sym> <preset>   Apply preset template")
    print(f"  Presets: {', '.join(PRESET_ALERTS.keys())}")
    print("  python main.py --alert-types                   List all 57 alert types")
    print("  python main.py --alert-remove <index>          Remove alert by index")
    print("")
    print("Other:")
    print("  python main.py --predict <sym>       AI price prediction (5-day)")
    print("  python main.py --sentiment <sym>     News sentiment (dictionary-based)")
    print("  python main.py --sentiment-llm <sym> LLM-powered sentiment (API + local cache)")
    print("  python main.py --sentiment-learned     Show learned sentiment store stats")
    print("  python main.py --chart <sym>         Interactive K-line chart (Plotly)")
    print("  python main.py --indicators <sym>    All 25+ technical indicators")
    print("  python main.py --ask <sym>           LLM AI analysis (DeepSeek)")
    print("")


def main():
    skill = StockAnalysisSkill()

    if len(sys.argv) < 2:
        print_usage()
        return

    cmd = sys.argv[1]

    # ── Market / Sectors ──
    if cmd == '--market':
        result = skill.market_overview()
        print(result)

    elif cmd == '--sectors':
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        result = skill.sector_ranking(n)
        print(result)

    # ── Report ──
    elif cmd == '--report':
        if len(sys.argv) < 3:
            print("Usage: python main.py --report <symbol>")
            return
        symbol = sys.argv[2]
        print(generate_report(symbol))

    # ── Backtesting (Enhanced) ──
    elif cmd in ('--backtest', '--bt-optimize', '--bt-monte', '--bt-chart'):
        if len(sys.argv) < 3:
            print(f"Usage: python main.py {cmd} <symbol> [strategy] [options]")
            return

        symbol = sys.argv[2]
        # Parse strategy and capital
        strategy = 'ma_cross'
        capital = 1_000_000
        extra_args = sys.argv[3:]

        for arg in extra_args:
            if arg in STRATEGIES:
                strategy = arg
            elif arg.replace('.', '').isdigit():
                capital = float(arg) if '.' in arg else int(arg)

        print(f"Loading data for {symbol} ({'optimize' if 'optimize' in cmd else 'backtest'})...")
        df = get_price_data(symbol, datalen=300)

        if df.empty:
            print(f"Error: No data for {symbol}")
            return

        engine = BacktestEngine()

        if cmd == '--backtest':
            # Run all or one
            if strategy in extra_args:
                strategies = [s for s in extra_args if s in STRATEGIES]
            else:
                strategies = [s for s in STRATEGIES if s not in ('turtle', 'grid')]
                # Default: show ma_cross, rsi, macd, bollinger
                strategies = [s for s in ['ma_cross', 'rsi', 'macd', 'bollinger'] if s in STRATEGIES]

            for s in strategies:
                try:
                    result = engine.run(df, strategy_name=s, symbol=symbol, initial_capital=capital)
                    if result and result.total_trades > 0:
                        print(format_backtest_result(result, show_trades=False))
                    else:
                        print(f"\n  {s}: no trades generated (strategy didn't fire)")
                except Exception as e:
                    print(f"\n  {s}: ERROR — {e}")

        elif cmd == '--bt-optimize':
            print(f"Optimizing {strategy} for {symbol}...")
            opt = engine.optimize(df, strategy, symbol, initial_capital=capital,
                                  max_combinations=30)
            print(f"\n  Best params: {opt.best_params}")
            print(f"  Best Sharpe: {opt.best_metric:.2f}")
            print(f"\n  Top 5 results:")
            for i, r in enumerate(opt.all_results[:5]):
                print(f"  {i+1}. {r['params']} | Sharpe={r['sharpe']:.2f} "
                      f"Return={r['total_return']:+.1f}% MaxDD={r['max_drawdown']:.1f}% "
                      f"WR={r['win_rate']:.0f}%")

        elif cmd == '--bt-monte':
            print(f"Monte Carlo simulation ({strategy}, 200 runs)...")
            mc = engine.monte_carlo(df, strategy, symbol, initial_capital=capital,
                                    n_simulations=200)
            print(f"\n  Monte Carlo Results ({strategy}):")
            for metric in ['sharpe', 'total_return', 'max_drawdown', 'final_capital']:
                if metric in mc:
                    v = mc[metric]
                    print(f"  {metric:16s}: mean={v.get('mean',0):.3f}  "
                          f"P5={v.get('p5',0):.3f}  P95={v.get('p95',0):.3f}")

        elif cmd == '--bt-chart':
            print(f"Generating equity curve chart ({strategy})...")
            result = engine.run(df, strategy_name=strategy, symbol=symbol, initial_capital=capital)
            chart_dir = os.path.join(os.path.dirname(__file__), 'charts')
            os.makedirs(chart_dir, exist_ok=True)
            path = os.path.join(chart_dir, f"{symbol}_{strategy}_equity.html")
            out = plot_equity_curve(result, path)
            print(f"Chart saved: {out}")

    # ── Alerts (Enhanced) ──
    elif cmd == '--alerts':
        engine = AlertEngine()
        print(engine.list_alerts())

    elif cmd == '--alert-add':
        if len(sys.argv) < 5:
            print("Usage: python main.py --alert-add <symbol> <type> <threshold> [message]")
            print(f"Types (57 available): {', '.join(ALL_ALERT_TYPES[:15])}...")
            print("Use --alert-types to see all")
            return
        engine = AlertEngine()
        msg = sys.argv[5] if len(sys.argv) > 5 else ""
        engine.add_alert(sys.argv[2], sys.argv[3], float(sys.argv[4]), msg)
        print(f"Alert added: {sys.argv[2]} {sys.argv[3]} threshold={sys.argv[4]}")

    elif cmd == '--alert-check':
        if len(sys.argv) < 3:
            print("Usage: python main.py --alert-check <symbol>")
            return
        symbol = sys.argv[2]
        print(f"Running full alert check for {symbol}...")
        df = get_price_data(symbol, datalen=120)
        if df.empty:
            print(f"Error: No data for {symbol}")
            return
        result = check_stock_alerts(symbol, df)
        print(result['report'])

    elif cmd == '--alert-preset':
        if len(sys.argv) < 4:
            print("Usage: python main.py --alert-preset <symbol> <preset>")
            print(f"Presets: {', '.join(PRESET_ALERTS.keys())}")
            for name, rules in PRESET_ALERTS.items():
                print(f"  {name}: {len(rules)} alerts — {rules[0][2]}")
            return
        engine = AlertEngine()
        count = apply_preset(engine, sys.argv[2], sys.argv[3])
        print(f"Applied preset '{sys.argv[3]}' to {sys.argv[2]}: {count} alerts added")
        print(engine.list_alerts(sys.argv[2]))

    elif cmd == '--alert-types':
        print(f"Available alert types ({len(ALL_ALERT_TYPES)} total):\n")
        for category, types in ALERT_CATEGORIES.items():
            print(f"  {category} ({len(types)}):")
            print(f"    {', '.join(types)}")
            print()

    elif cmd == '--alert-remove':
        if len(sys.argv) < 3:
            print("Usage: python main.py --alert-remove <index>")
            print("Use --alerts to see indices")
            return
        engine = AlertEngine()
        idx = int(sys.argv[2])
        engine.remove_alert(idx)
        print(f"Removed alert [{idx}]")
        print(engine.list_alerts())

    # ── Predict ──
    elif cmd == '--predict':
        if len(sys.argv) < 3:
            print("Usage: python main.py --predict <symbol>")
            return
        symbol = sys.argv[2]
        df = get_price_data(symbol, datalen=100)
        result = predict_price(df, horizon=5)
        print(format_prediction_report(result))

    # ── Chart ──
    elif cmd == '--chart':
        if len(sys.argv) < 3:
            print("Usage: python main.py --chart <symbol>")
            return
        symbol = sys.argv[2]
        print(f"Generating interactive chart for {symbol}...")
        try:
            df = get_price_data(symbol, datalen=200)
            indicators = get_trend_detail(df) if not df.empty else {}
            path = plotly_chart(df, indicators=indicators, symbol=symbol)
            if path:
                print(f"Chart saved: {path}")
        except Exception as e:
            print(f"Error: {e}")

    # ── Technical Indicators ──
    elif cmd == '--indicators':
        if len(sys.argv) < 3:
            print("Usage: python main.py --indicators <symbol>")
            return
        symbol = sys.argv[2]
        df = get_price_data(symbol, datalen=120)
        if df.empty:
            print(f"Error: No data for {symbol}")
            return
        indicators = get_trend_detail(df)
        patterns = detect_candlestick_patterns(df)
        anomaly = detect_price_anomaly(df)

        print(get_indicator_summary(indicators))
        print()
        active_patterns = [k for k, v in patterns.items() if v]
        if active_patterns:
            print(f"Candlestick Patterns: {', '.join(active_patterns)}")
        else:
            print("Candlestick Patterns: none detected")
        if anomaly['anomaly']:
            print(f"Price Anomaly: z={anomaly['anomaly_z_score']:.2f} {anomaly['anomaly_direction']}")

    # ── Ask (LLM) ──
    elif cmd == '--ask':
        if len(sys.argv) < 3:
            print("Usage: python main.py --ask <symbol>")
            return
        symbol = sys.argv[2]
        print(llm_analyze(symbol))

    # ── Sentiment ──
    elif cmd == '--sentiment-llm':
        if len(sys.argv) < 3:
            print("Usage: python main.py --sentiment-llm <symbol>")
            print("  Uses DeepSeek LLM API for nuanced sentiment analysis")
            print("  Results are cached locally -> reduces future API costs")
            return
        symbol = sys.argv[2].upper()
        force = '--no-cache' in sys.argv
        print(f"LLM Sentiment Analysis for {symbol}...")
        try:
            result = get_sentiment_for_stock(symbol, use_llm=True, use_cache=not force)
            print_llm_sentiment(result)
        except Exception as e:
            print(f"  LLM Error: {e}")
            print("  Falling back to dictionary-based analysis...")
            result = get_sentiment_for_stock(symbol, use_llm=False)

    elif cmd == '--sentiment-learned':
        store = SentimentLearnedStore()
        stats = store.stats()
        print("=" * 50)
        print("  Sentiment Learning Store")
        print("=" * 50)
        print(f"  Total learned: {stats['total_learned']}")
        print(f"    Bullish:  {stats['bullish']}")
        print(f"    Bearish:  {stats['bearish']}")
        print(f"    Neutral:  {stats['neutral']}")
        print(f"  Models used: {stats['models_used']}")
        print(f"  Store: {stats['store_path']}")
        print("=" * 50)

    elif cmd == '--sentiment':
        if len(sys.argv) < 3:
            print("Usage: python main.py --sentiment <symbol>")
            return
        symbol = sys.argv[2].upper()
        print(f"Analyzing news sentiment for {symbol}...")
        try:
            result = get_sentiment_for_stock(symbol)
            ss = result.get('stock_sentiment', {})
            print()
            print("=" * 60)
            print(f"  Sentiment Analysis: {symbol}")
            print("=" * 60)
            emoji = {'bullish': '🟢', 'neutral': '🟡', 'bearish': '🔴'}.get(
                ss.get('overall_label', 'neutral'), '⚪')
            label_cn = {'bullish': '看多', 'neutral': '中性', 'bearish': '看空'}.get(
                ss.get('overall_label', ''), '?')
            print(f"  Overall:  {emoji} {ss.get('overall_score', 0):+.3f} ({label_cn})")
            print(f"  Articles: {ss.get('article_count', 0)} "
                  f"(bullish:{ss.get('bullish_count',0)} "
                  f"neutral:{ss.get('neutral_count',0)} "
                  f"bearish:{ss.get('bearish_count',0)})")
            print(f"  Trend:    {ss.get('sentiment_trend', 'stable')}")
            print()
            print("  Key terms:")
            for term, cnt in ss.get('top_positive_terms', [])[:5]:
                print(f"    🟢 {term} ({cnt})")
            for term, cnt in ss.get('top_negative_terms', [])[:5]:
                print(f"    🔴 {term} ({cnt})")
            print()
            print("  Recent headlines:")
            for art in ss.get('articles', [])[:10]:
                e = {'bullish': '🟢', 'neutral': '🟡', 'bearish': '🔴'}.get(art['label'], '⚪')
                print(f"    {e} {art.get('date','')} | {art['title'][:70]}")
            print("=" * 60)
        except Exception as e:
            print(f"  Error: {e}")
            print("  (News analysis requires network access to Sina Finance)")

    # ── Default: analyze single stock ──
    else:
        result = skill.analyze_stock(cmd)
        print(result)


def print_llm_sentiment(result):
    """Pretty-print LLM sentiment results."""
    ss = result.get('stock_sentiment', {})
    print()
    print("=" * 60)
    print(f"  LLM Sentiment Analysis: {result.get('symbol', '?')}")
    print("=" * 60)
    source = "🧠 LLM" if result.get('llm_used') else "📖 Dictionary (fallback)"
    emoji = {'bullish': '🟢', 'neutral': '🟡', 'bearish': '🔴'}.get(
        ss.get('overall_label', 'neutral'), '⚪')
    label_cn = {'bullish': '看多', 'neutral': '中性', 'bearish': '看空'}.get(
        ss.get('overall_label', ''), '?')
    print(f"  Source:   {source}")
    print(f"  Overall:  {emoji} {ss.get('overall_score', 0):+.3f} ({label_cn})")
    print(f"  Articles: {ss.get('article_count', 0)} "
          f"(bullish:{ss.get('bullish_count',0)} "
          f"neutral:{ss.get('neutral_count',0)} "
          f"bearish:{ss.get('bearish_count',0)})")
    print(f"  Trend:    {ss.get('sentiment_trend', 'stable')}")
    if result.get('api_calls', 0) > 0:
        print(f"  API:      {result['api_calls']} calls, {result.get('cache_hits', 0)} cache hits")
    print()
    themes = result.get('key_themes', [])
    if themes:
        print("  Key themes:")
        for theme, count in themes[:6]:
            print(f"    · {theme} ({count})")
        print()
    print("  Articles:")
    for art in result.get('articles', [])[:12]:
        e = {'bullish': '🟢', 'neutral': '🟡', 'bearish': '🔴'}.get(art.get('label', 'neutral'), '⚪')
        src = art.get('source', '?')
        conf = art.get('confidence', 0)
        reasoning = art.get('reasoning', '')
        print(f"    {e} [{src:5s}] c={conf:.1f} {art['score']:+.1f} | {art['title'][:55]}")
        if reasoning and reasoning not in ('dictionary_fallback', 'no_api_key', 'empty_title'):
            print(f"       ↳ {reasoning}")
    print("=" * 60)

if __name__ == "__main__":
    main()
