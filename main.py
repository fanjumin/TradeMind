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
from analysis.social_sentiment import analyze_social_sentiment, print_social_sentiment, print_store_stats as print_social_stats
from analysis.llm_advisor import analyze_report as llm_analyze
from analysis.predict import predict_stock, print_prediction
from strategy_market import list_strategies, compare_strategies, rank_strategies, categories_summary


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
    print("  python main.py --predict <sym>       ML + LSTM price prediction (5-day)")
    print("  python main.py --predict-llm <sym>    Above + DeepSeek LLM synthesis")
    print("  python main.py --financials <sym>     Financial report (三表+评分)")
    print("  python main.py --factors [symbols..]  Factor analysis (IC+分层回测)")
    print("")
    print("Strategy Marketplace (v2.5):")
    print("  python main.py --strategies               List all strategies with metadata")
    print("  python main.py --strategies compare <sym> Compare all strategies on a stock")
    print("  python main.py --strategies rank [metric] Rank strategies by metric")
    print("  python main.py --strategies categories    Category overview")
    print("")
    print("Multi-Asset (v2.5):")
    print("  python main.py --etf list                 List all ETFs (1469 total)")
    print("  python main.py --etf search <keyword>      Search ETFs")
    print("  python main.py --etf <code>               ETF quote (e.g., 510050)")
    print("  python main.py --cb list                  List active convertible bonds")
    print("  python main.py --cb search <keyword>       Search CBs")
    print("  python main.py --cb <code>                CB quote (e.g., 110044)")
    print("")
    print("Simulated Trading (v2.5):")
    print("  python main.py --trade init [capital]        Initialize account")
    print("  python main.py --trade buy <sym> [qty]       Market buy")
    print("  python main.py --trade sell <sym> [qty]      Market sell")
    print("  python main.py --trade positions             View positions")
    print("  python main.py --trade performance           Performance report")
    print("  python main.py --trade orders                View orders")
    print("  python main.py --trade history               Trade history")
    print("  python main.py --trade tick                  Update prices")
    print("  python main.py --trade reset                 Reset account")
    print("")
    print("Retail Daily Picks (v2.6):")
    print("  python main.py --daily                       Today's top picks")
    print("  python main.py --daily --top 5               Top 5 picks")
    print("  python main.py --daily --wechat              WeChat format")
    print("  python main.py --talk <symbol>               Plain-language analysis")
    print("  python main.py --watch                       Monitor your watchlist")
    print("  python main.py --watch add <symbol>           Add to watchlist")
    print("  python main.py --watch remove <symbol>        Remove from watchlist")
    print("  python main.py --ralerts                     Scan for retail alerts")
    print("  python main.py --ralerts --wechat            Alerts in WeChat format")
    print("  python main.py --sentiment <sym>     News sentiment (dictionary-based)")
    print("  python main.py --sentiment-llm <sym> LLM-powered sentiment (API + local cache)")
    print("  python main.py --sentiment-learned     Show learned sentiment store stats")
    print("  python main.py --sentiment-social <sym> Social sentiment (Guba forum + LLM)")
    print("  python main.py --sentiment-social-stats  Show social sentiment cache stats")
    print("  python main.py --chart <sym>         Interactive K-line chart (Plotly)")
    print("  python main.py --indicators <sym>    All 25+ technical indicators")
    print("  python main.py --ask <sym>           LLM AI analysis (DeepSeek)")
    print("")


def main():

    # Financial analysis (v2.5) — baostock三表分析
    if "--financials" in sys.argv:
        symbol = sys.argv[-1] if len(sys.argv) > 2 and not sys.argv[-1].startswith("--") else "600519"
        from analysis.financials import print_financial_report
        print_financial_report(symbol)
        sys.exit(0)
    # Factor analysis (v2.5)
    if "--factors" in sys.argv:
        from analysis.factors import full_factor_analysis
        # Extract symbols after --factors
        idx = sys.argv.index("--factors")
        universe = sys.argv[idx+1:] if idx+1 < len(sys.argv) else None
        full_factor_analysis(universe)
        sys.exit(0)

        # ETF data (v2.5 Phase 2)
    if "--etf" in sys.argv:
        from data.etf import fetch_etf_list, get_etf_price, search_etfs
        idx = sys.argv.index("--etf")
        sub = sys.argv[idx+1] if idx+1 < len(sys.argv) else "list"
        
        if sub == "list":
            etfs = fetch_etf_list()
            print(f"\nETF 总数: {len(etfs)}")
            # By type
            types = {}
            for e in etfs:
                t = e.get('etf_type', '其他')
                types[t] = types.get(t, 0) + 1
            for t, c in sorted(types.items()):
                print(f"  {t}: {c} 只")
            print(f"\n热门 ETF (前15):")
            from data.etf import get_popular_etfs
            for e in get_popular_etfs()[:15]:
                print(f"  {e['code']} {e['name']} [{e.get('etf_type','?')}]")
        elif sub == "search":
            q = sys.argv[idx+2] if idx+2 < len(sys.argv) else ""
            results = search_etfs(q)
            print(f"\n搜索 '{q}': {len(results)} 结果")
            for r in results[:15]:
                print(f"  {r['code']} {r['name']} [{r.get('etf_type','?')}]")
        else:
            # Assume it's a code
            p = get_etf_price(sub)
            if p:
                print(f"\n{p['code']} {p['name']} [ETF]")
                print(f"  价格: {p['price']}  涨跌: {p['change_pct']:+.2f}%")
                if p.get('pe'):
                    print(f"  PE: {p['pe']}")
            else:
                print(f"ETF {sub} 未找到")
        sys.exit(0)
    
    # Convertible bond data (v2.5 Phase 2)
    if "--cb" in sys.argv:
        from data.convertible import fetch_cb_list, get_cb_price, search_cb
        idx = sys.argv.index("--cb")
        sub = sys.argv[idx+1] if idx+1 < len(sys.argv) else "list"
        
        if sub == "list":
            cbs = fetch_cb_list()
            print(f"\n可转债总数: {len(cbs)} (活跃)")
            for cb in cbs[:20]:
                print(f"  {cb['code']} {cb['name']} -> {cb['stock_code']} | {cb.get('rating','?')} | {cb.get('expire_date','?')}")
        elif sub == "search":
            q = sys.argv[idx+2] if idx+2 < len(sys.argv) else ""
            results = search_cb(q)
            print(f"\n搜索 '{q}': {len(results)} 结果")
            for r in results[:15]:
                print(f"  {r['code']} {r['name']} -> {r['stock_code']}")
        else:
            p = get_cb_price(sub)
            if p:
                print(f"\n{p['code']} {p['name']} [可转债]")
                print(f"  价格: {p['price']}  涨跌: {p['change_pct']:+.2f}%")
            else:
                print(f"可转债 {sub} 未找到")
        sys.exit(0)
    
    # Simulated trading (v2.5 Phase 2)
    if "--trade" in sys.argv:
        from sim_trade import OrderManager, OrderSide, OrderType
        om = OrderManager()
        idx = sys.argv.index("--trade")
        sub = sys.argv[idx+1] if idx+1 < len(sys.argv) else "status"
        
        if sub == "init":
            capital = float(sys.argv[idx+2]) if idx+2 < len(sys.argv) else 1000000
            om.cash = capital
            om.initial_capital = capital
            om.orders = {}
            om.positions = {}
            om.trades = []
            om.snapshots = []
            om._save_state()
            print(f"Account initialized with {capital:,.0f}")
        
        elif sub == "buy":
            symbol = sys.argv[idx+2] if idx+2 < len(sys.argv) else "600519"
            qty = int(sys.argv[idx+3]) if idx+3 < len(sys.argv) else 100
            result = om.submit_order(symbol, symbol, OrderSide.BUY, OrderType.MARKET, qty)
            if result.get('error'):
                print(f"Error: {result['error']}")
            else:
                print(f"Bought {qty} shares of {symbol}")
                om.tick([symbol])
            om.get_summary()
        
        elif sub == "sell":
            symbol = sys.argv[idx+2]
            qty = int(sys.argv[idx+3]) if idx+3 < len(sys.argv) else 0
            if qty == 0 and symbol in om.positions:
                qty = om.positions[symbol].quantity
            name = om.positions.get(symbol, type('',(),{'name':symbol})()).name if hasattr(om.positions.get(symbol, None), 'name') else symbol
            try:
                name = om.positions[symbol].name
            except:
                name = symbol
            result = om.submit_order(symbol, name, OrderSide.SELL, OrderType.MARKET, qty)
            if result.get('error'):
                print(f"Error: {result['error']}")
            else:
                print(f"Sold {qty} shares of {symbol}")
                om.tick([symbol])
            om.get_summary()
        
        elif sub in ("pos", "positions"):
            positions = om.get_positions()
            if not positions:
                print("No positions")
            else:
                print(f"\n{'Symbol':<8s} {'Name':<16s} {'Qty':>6s} {'AvgCost':>10s} {'Price':>10s} {'PnL%':>8s}")
                print("-" * 65)
                for p in positions:
                    print(f"{p['symbol']:<8s} {p['name']:<16s} {p['quantity']:>6d} {p['avg_cost']:>10.2f} {p['current_price']:>10.2f} {p['pnl_pct']:>+7.2f}%")
        
        elif sub in ("perf", "performance"):
            om.get_summary()
        
        elif sub == "orders":
            orders = om.get_orders()
            pending = [o for o in orders if o['status'] == 'pending']
            filled = [o for o in orders if o['status'] == 'filled']
            print(f"\nOrders: {len(pending)} pending, {len(filled)} filled")
            for o in pending:
                print(f"  [{o['order_id']}] {o['side']} {o['symbol']} x{o['quantity']} limit={o['limit_price']}")
        
        elif sub == "history":
            trades = om.get_trades()
            print(f"\nTrade History ({len(trades)}):")
            for t in trades[-20:]:
                print(f"  {t['timestamp'][:19]} {t['side']:4s} {t['symbol']} x{t['quantity']} @{t['price']:.2f}")
        
        elif sub == "tick":
            r = om.tick()
            print(f"Tick: {r['prices']} prices updated, total={r['total_value']:,.0f}")
        
        elif sub == "reset":
            om.cash = om.initial_capital
            om.orders = {}
            om.positions = {}
            om.trades = []
            om.snapshots = []
            om._save_state()
            print(f"Reset to {om.initial_capital:,.0f}")
        
        else:
            om.get_summary()
        
        sys.exit(0)
    
    # Plain-talk analysis (v2.6 Phase 3)
    if "--talk" in sys.argv:
        sym = sys.argv[sys.argv.index("--talk")+1] if len(sys.argv) > sys.argv.index("--talk")+1 else "600519"
        from plain_talk import plain_talk
        print(plain_talk(sym))
        sys.exit(0)
    
    # Watchlist monitor (v2.6 Phase 3)
    if "--watch" in sys.argv:
        from watchlist_monitor import monitor, fmt_monitor, load_watchlist, save_watchlist
        idx = sys.argv.index("--watch")
        sub = sys.argv[idx+1] if idx+1 < len(sys.argv) else "show"
        if sub == "add":
            sym = sys.argv[idx+2]
            wl = load_watchlist()
            if sym not in wl:
                wl.append(sym); save_watchlist(wl)
                print(f"Added {sym} to watchlist ({len(wl)} stocks)")
            else:
                print(f"{sym} already in watchlist")
        elif sub == "remove":
            sym = sys.argv[idx+2]
            wl = load_watchlist()
            if sym in wl:
                wl.remove(sym); save_watchlist(wl)
                print(f"Removed {sym} ({len(wl)} stocks)")
        elif sub == "list":
            wl = load_watchlist()
            print(f"Watchlist ({len(wl)}): {', '.join(wl)}")
        else:
            r = monitor()
            print(fmt_monitor(r))
        sys.exit(0)
    
    # Retail alerts (v2.6 Phase 3)
    if "--ralerts" in sys.argv:
        from retail_alerts import scan_alerts, fmt_alerts, fmt_wechat
        wechat = "--wechat" in sys.argv
        alerts = scan_alerts()
        if wechat:
            print(fmt_wechat(alerts))
        else:
            print(fmt_alerts(alerts))
        sys.exit(0)
    
    # Daily picks for retail investors (v2.6 Phase 3)
    if "--daily" in sys.argv:
        from daily_picks import daily_picks, fmt, fmt_wechat
        top = 8
        if "--top" in sys.argv:
            ti = sys.argv.index("--top")
            top = int(sys.argv[ti+1]) if ti+1 < len(sys.argv) else 8
        wechat = "--wechat" in sys.argv
        result = daily_picks(top_n=top)
        if wechat:
            print(fmt_wechat(result))
        else:
            print(fmt(result))
        sys.exit(0)
    
    # Strategy marketplace (v2.5 Phase 2)
    if "--strategies" in sys.argv:
        idx = sys.argv.index("--strategies")
        sub = sys.argv[idx+1] if idx+1 < len(sys.argv) else "list"
        
        if sub == "compare":
            symbol = sys.argv[idx+2] if idx+2 < len(sys.argv) else "600519"
            days = int(sys.argv[idx+3]) if idx+3 < len(sys.argv) else 252
            result = compare_strategies(symbol, days=days)
            if 'error' in result:
                print(f"Error: {result['error']}")
            else:
                sep = "=" * 80
                print()
                print(sep)
                print(f"  策略比较 — {symbol} (回测 {days} 天)")
                print(sep)
                header = f"  {'策略':<18s} {'类别':<14s} {'Sharpe':>7s} {'收益%':>8s} {'回撤%':>7s} {'胜率%':>6s} {'交易':>5s} {'盈亏比':>6s}"
                print(header)
                print("  " + "-" * 80)
                for r in result['results']:
                    if r.get('error'):
                        print(f"  {r['key']:<16s} ERR: {r['error']}")
                    else:
                        print(f"  {r['key']:<16s} {r['category']:<14s} {r.get('sharpe_ratio',0):>7.2f} {r.get('total_return',0):>8.2f} {r.get('max_drawdown',0):>7.2f} {r.get('win_rate',0):>6.1f} {r.get('total_trades',0):>5d} {r.get('profit_factor',0):>6.2f}")
        
        elif sub == "rank":
            metric = sys.argv[idx+2] if idx+2 < len(sys.argv) else "sharpe_ratio"
            result = rank_strategies(metric=metric)
            print(f"\n策略排名 (按 {metric}):")
            for i, r in enumerate(result['ranking'], 1):
                m = r.get('avg_sharpe', 0) if metric == 'sharpe_ratio' else r.get('avg_return', 0)
                print(f"  {i:2d}. {r['name']:<20s} {m:>8.3f}")
        
        elif sub == "categories":
            result = categories_summary()
            print("\n策略类别分布:")
            for c in result['categories']:
                print(f"  [{c['name']}] {c['count']}个策略 — {c['description']}")
        
        else:  # list
            strategies = list_strategies()
            sep = "=" * 80
            print()
            print(sep)
            print(f"  策略市场 — {len(strategies)} 个策略")
            print(sep)
            for s in strategies:
                print(f"\n  [{s['key']}] {s['name']}")
                print(f"  类别: {s['category']} | 风险: {s['risk_level']} | 周期: {s['timeframe']}")
                print(f"  描述: {s['description']}")
                print(f"  标签: {', '.join(s['tags'])}")
                if s['default_params']:
                    print(f"  参数: {s['default_params']}")
        sys.exit(0)
    
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
    elif cmd == '--predict-llm':
        if len(sys.argv) < 3:
            print("Usage: python main.py --predict-llm <symbol>")
            print("  Runs ML + LSTM prediction, then DeepSeek LLM synthesis")
            return
        symbol = sys.argv[2].upper()
        print(f"Running {symbol} prediction with LLM synthesis...")
        try:
            result = predict_stock(symbol, use_llm=True)
            print_prediction(result)
        except Exception as e:
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()

    elif cmd == '--predict':
        if len(sys.argv) < 3:
            print("Usage: python main.py --predict <symbol>")
            print("  ML ensemble (RF+GBDT+Ridge) + LSTM deep learning")
            return
        symbol = sys.argv[2].upper()
        print(f"Running {symbol} prediction...")
        try:
            result = predict_stock(symbol, use_llm=False)
            print_prediction(result)
            # Auto-generate chart with prediction overlay
            df = get_price_data(symbol, datalen=200)
            if not df.empty:
                try:
                    ind = get_trend_detail(df) if not df.empty else {}
                    chart_path = plotly_chart(df, indicators=ind, symbol=symbol,
                                              prediction=result, days=120)
                    if chart_path:
                        print(f"  📊 预测图表: {chart_path}")
                except Exception:
                    pass  # Chart is optional
        except Exception as e:
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()

    # ── Chart ──
    elif cmd == '--chart':
        if len(sys.argv) < 3:
            print("Usage: python main.py --chart <symbol> [--with-predict] [--with-sentiment]")
            return
        symbol = sys.argv[2]
        with_predict = '--with-predict' in sys.argv
        with_sentiment = '--with-sentiment' in sys.argv
        print(f"Generating interactive chart for {symbol}...")
        try:
            df = get_price_data(symbol, datalen=200)
            if df.empty:
                print(f"Error: No data for {symbol}")
                return
            indicators = get_trend_detail(df) if not df.empty else {}

            prediction = None
            if with_predict:
                try:
                    prediction = predict_stock(symbol, use_llm=False)
                except Exception as e:
                    print(f"  Prediction skipped: {e}")

            sentiment_data = None
            if with_sentiment:
                try:
                    sentiment_data = analyze_social_sentiment(symbol, force_llm=False)
                except Exception as e:
                    print(f"  Sentiment skipped: {e}")

            path = plotly_chart(df, indicators=indicators, symbol=symbol,
                                prediction=prediction, sentiment=sentiment_data)
            if path:
                print(f"Chart saved: {path}")
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

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

    elif cmd == '--sentiment-social':
        if len(sys.argv) < 3:
            print("Usage: python main.py --sentiment-social <symbol>")
            print("  Fetches Guba forum posts and analyzes via DeepSeek LLM")
            print("  Results cached -> future runs skip API for same posts")
            return
        symbol = sys.argv[2].upper()
        force = '--no-cache' in sys.argv
        print(f"Social Sentiment Analysis for {symbol}...")
        try:
            result = analyze_social_sentiment(symbol, force_llm=force)
            print_social_sentiment(result)
        except Exception as e:
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()

    elif cmd == '--sentiment-social-stats':
        print_social_stats()

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
