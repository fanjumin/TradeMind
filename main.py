import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from skill import StockAnalysisSkill
from report import generate_report
from backtest import run_backtest, format_backtest_report
from data.price import get_price_data, get_latest_price
from analysis.technical import get_trend_detail
from predict import predict_price, format_prediction_report
from alerts import AlertEngine, generate_alert_report
from data.news import get_stock_news
from analysis.sentiment import analyze_news, get_sentiment_for_stock


def main():
    skill = StockAnalysisSkill()
    
    if len(sys.argv) < 2:
        print("TradeMind - A-Stock Analysis Tool")
        print("Usage:")
        print("  python main.py <symbol>          Analyze stock (e.g., 000001, 600519)")
        print("  python main.py --market          Market overview (all major indices)")
        print("  python main.py --sectors [N]     Top N sector ranking (default: 10)")
        print("  python main.py --report <symbol> Full analysis report")
        print("  python main.py --backtest <sym>  Backtest strategies (ma_cross/rsi/kdj)")
        print("  python main.py --backtest <sym> <strat>  Specific strategy")
        print("  python main.py --predict <sym>   AI price prediction (5-day)")
        print("  python main.py --alerts          List configured alerts")
        print("  python main.py --alert-add <sym> <type> <threshold>")
        print("  python main.py --alert-check <sym>  Check alerts for a stock")
        print("  python main.py --sentiment <sym>   News sentiment analysis")
        return
    
    cmd = sys.argv[1]
    
    if cmd == '--market':
        result = skill.market_overview()
        print(result)
    elif cmd == '--sectors':
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        result = skill.sector_ranking(n)
        print(result)
    elif cmd == '--report':
        if len(sys.argv) < 3:
            print("Usage: python main.py --report <symbol>")
            return
        report = generate_report(sys.argv[2])
        print(report)
    elif cmd == '--backtest':
        if len(sys.argv) < 3:
            print("Usage: python main.py --backtest <symbol> [strategy]")
            print("Strategies: ma_cross, rsi, kdj, ma_rsi_combined (default: all)")
            return
        symbol = sys.argv[2]
        df = get_price_data(symbol, datalen=200)
        capital = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else 1000000
        
        if len(sys.argv) > 3 and not sys.argv[3].isdigit():
            strategies = [sys.argv[3]]
        else:
            strategies = ['ma_cross', 'rsi', 'kdj']
        
        for strat in strategies:
            result = run_backtest(df, strategy_name=strat, symbol=symbol, initial_capital=capital)
            print(format_backtest_report(result))
            print()
    elif cmd == '--predict':
        if len(sys.argv) < 3:
            print("Usage: python main.py --predict <symbol>")
            return
        symbol = sys.argv[2]
        df = get_price_data(symbol, datalen=100)
        result = predict_price(df, horizon=5)
        print(format_prediction_report(result))

    elif cmd == '--alerts':
        engine = AlertEngine()
        if len(sys.argv) > 2:
            sub = sys.argv[2]
            if sub == 'add' and len(sys.argv) >= 6:
                engine.add_alert(sys.argv[3], sys.argv[4], float(sys.argv[5]))
                print(f"Alert added: {sys.argv[3]} {sys.argv[4]} {sys.argv[5]}")
            elif sub == 'check' and len(sys.argv) >= 4:
                symbol = sys.argv[3]
                info = get_latest_price(symbol)
                df = get_price_data(symbol, datalen=60)
                indicators = get_trend_detail(df) if not df.empty else {}
                price = info['price'] if info else 0
                triggered = engine.check_alerts(symbol, price, indicators)
                print(generate_alert_report(symbol, price, indicators, triggered))
            else:
                print(engine.list_alerts())
        else:
            print(engine.list_alerts())

    elif cmd == '--alert-add':
        if len(sys.argv) < 5:
            print("Usage: python main.py --alert-add <symbol> <type> <threshold>")
            print("Types: price_above, price_below, rsi_oversold, rsi_overbought, volume_surge")
            return
        engine = AlertEngine()
        engine.add_alert(sys.argv[2], sys.argv[3], float(sys.argv[4]))
        print(f"Alert added: {sys.argv[2]} {sys.argv[3]} {sys.argv[4]}")

    elif cmd == '--alert-check':
        if len(sys.argv) < 3:
            print("Usage: python main.py --alert-check <symbol>")
            return
        engine = AlertEngine()
        symbol = sys.argv[2]
        info = get_latest_price(symbol)
        df = get_price_data(symbol, datalen=60)
        indicators = get_trend_detail(df) if not df.empty else {}
        price = info['price'] if info else 0
        triggered = engine.check_alerts(symbol, price, indicators)
        print(generate_alert_report(symbol, price, indicators, triggered))

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

    else:
        result = skill.analyze_stock(cmd)
        print(result)


if __name__ == "__main__":
    main()
