import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.price import get_price_data, get_latest_price
from data.fund import get_fund_flow
from data.basic import get_basic_info, get_basic_score
from data.index import get_all_indices_status
from data.sector import get_top_sectors
from analysis.technical import get_trend, get_trend_detail
from analysis.scoring import get_score, get_signal, get_signal_cn


def generate_report(symbol):
    lines = []
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    lines.append('=' * 60)
    lines.append('  TradeMind - A-Stock Analysis Report')
    lines.append('  Time: ' + now)
    lines.append('  Stock: ' + symbol)
    lines.append('=' * 60)

    # Real-time price
    try:
        info = get_latest_price(symbol)
        if info:
            lines.append('')
            lines.append('--- Real-Time Quote ---')
            lines.append('  Name:       ' + info.get('name', ''))
            lines.append('  Price:      %.2f' % info['price'])
            lines.append('  Change:     %+.2f (%+.2f%%)' % (info['change'], info['change_pct']))
            lines.append('  High:       %.2f' % info['high'])
            lines.append('  Low:        %.2f' % info['low'])
            lines.append('  Open:       %.2f' % info['open'])
            lines.append('  Volume:     %.0f' % info['volume'])
    except Exception as e:
        lines.append('  [Real-time error: %s]' % str(e))

    # K-line trend
    try:
        df = get_price_data(symbol)
        detail = get_trend_detail(df)
        trend = detail.get('trend', 'neutral')

        lines.append('')
        lines.append('--- Technical Analysis ---')
        lines.append('  Close:      %.2f' % detail['close'])
        lines.append('  MA5:        %.2f' % detail['ma5'])
        lines.append('  MA10:       %.2f' % detail['ma10'])
        lines.append('  MA20:       %.2f' % detail['ma20'])
        lines.append('  MA60:       %.2f' % detail['ma60'])
        lines.append('  MACD:       %.2f' % detail['macd'])
        lines.append('  Trend:      ' + trend)

        close = detail['close']
        ma5 = detail.get('ma5', 0)
        ma20 = detail.get('ma20', 0)
        ma60 = detail.get('ma60', 0)
        if ma5 > 0 and ma20 > 0 and ma60 > 0:
            if close > ma5 > ma20 > ma60:
                lines.append('  Alignment:  Bullish (price > MA5 > MA20 > MA60)')
            elif close < ma5 < ma20 < ma60:
                lines.append('  Alignment:  Bearish (price < MA5 < MA20 < MA60)')
            else:
                lines.append('  Alignment:  Mixed')
    except Exception as e:
        lines.append('  [K-line error: %s]' % str(e))
        trend = 'neutral'
        detail = {}

    # Fund flow
    try:
        fund_total, fund_detail = get_fund_flow(symbol)
        lines.append('')
        lines.append('--- Volume & Flow ---')
        lines.append('  Volume:     %.0f' % fund_detail.get('volume', 0))
        lines.append('  Amount:     %.0f' % fund_detail.get('amount', 0))
        lines.append('  Flow Score: %.2f' % fund_total)
        if fund_total > 0:
            lines.append('  Signal:     Positive (price up + volume)')
        else:
            lines.append('  Signal:     Negative (price down)')
    except Exception as e:
        lines.append('  [Flow error: %s]' % str(e))
        fund_total = 0

    # Fundamentals - enhanced with ROE, margins, growth
    try:
        basic = get_basic_info(symbol)
        basic_score, basic_reasons = get_basic_score(basic)
        lines.append('')
        lines.append('--- Fundamentals ---')
        company = basic.get('company', 'N/A')
        pe = basic.get('pe_ttm', 0)
        pb = basic.get('pb', 0)
        eps = basic.get('eps_ttm', 0)
        tr = basic.get('turnover_rate', 0)
        roe = basic.get('roe', 0)
        npm = basic.get('np_margin', 0)
        gpm = basic.get('gp_margin', 0)
        yoy_ni = basic.get('yoy_net_income', 0)
        yoy_eps = basic.get('yoy_eps', 0)
        net_profit = basic.get('net_profit', 0)
        revenue = basic.get('revenue', 0)

        lines.append('  Company:    ' + company)
        if pe > 0: lines.append('  PE (TTM):   %.2f' % pe)
        if pb > 0: lines.append('  PB:         %.2f' % pb)
        if eps > 0: lines.append('  EPS (TTM):  %.2f' % eps)
        if tr > 0: lines.append('  Turnover:   %.2f%%' % tr)
        if roe > 0: lines.append('  ROE:        %.1f%%' % (roe * 100))
        if npm > 0: lines.append('  Net Margin: %.1f%%' % (npm * 100))
        if gpm > 0: lines.append('  Gross Marg: %.1f%%' % (gpm * 100))
        if revenue > 0: lines.append('  Revenue:    %.1fB' % (revenue / 1e8))
        if net_profit > 0: lines.append('  Net Profit: %.1fB' % (net_profit / 1e8))
        if yoy_ni != 0: lines.append('  YOY NetIn:  %+.1f%%' % (yoy_ni * 100))
        if yoy_eps != 0: lines.append('  YOY EPS:    %+.1f%%' % (yoy_eps * 100))
        lines.append('  Score:      %d/100' % basic_score)
        for r in basic_reasons:
            lines.append('    - ' + r)
    except Exception as e:
        lines.append('  [Fundamental error: %s]' % str(e))
        basic_score = 0

    # Overall
    score = get_score(trend, fund_total, basic_score)
    signal = get_signal(score)
    signal_cn = get_signal_cn(signal)

    lines.append('')
    lines.append('--- Overall ---')
    lines.append('  Score:      %d/100' % score)
    lines.append('  Signal:     %s (%s)' % (signal_cn, signal))

    summaries = {
        'strong_buy': 'Strong bullish across dimensions',
        'buy': 'Mostly positive, watch for entry',
        'hold': 'Mixed signals, cautious holding',
        'reduce': 'Bearish tendency, consider reducing',
        'avoid': 'Strong bearish, avoid',
    }
    lines.append('  Summary:    ' + summaries.get(signal, ''))

    lines.append('')
    lines.append('=' * 60)
    lines.append('  Disclaimer: Automated analysis, not investment advice.')
    lines.append('=' * 60)

    return chr(10).join(lines)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(generate_report(sys.argv[1]))
    else:
        print("Usage: python report.py <symbol>")
