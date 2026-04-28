#!/usr/bin/env python3
import sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)

def morning_report():
    from daily_picks import daily_picks, fmt_wechat as fmt_picks
    from data.index import get_all_indices_status
    now = datetime.now()
    lines = ['Morning Market Scan ' + now.strftime('%m/%d'), '']
    try:
        indices = get_all_indices_status()
        if indices:
            lines.append('Market:')
            for idx in indices[:4]:
                n = idx.get('name','?')
                c = idx.get('change_pct', 0)
                lines.append('  ' + n + ': ' + format(c, '+.2f') + '%')
    except:
        lines.append('Market: data unavailable')
    lines.append('')
    try:
        picks = daily_picks(top_n=5)
        lines.append(fmt_picks(picks))
    except Exception as e:
        lines.append('Scan unavailable: ' + str(e))
    return NL.join(lines)

def evening_report():
    from daily_picks import scan_market, score_stock
    from data.index import get_all_indices_status
    now = datetime.now()
    lines = ['Evening Market Scan ' + now.strftime('%m/%d'), '']
    try:
        indices = get_all_indices_status()
        if indices:
            lines.append('Market Close:')
            for idx in indices[:4]:
                n = idx.get('name','?')
                c = idx.get('change_pct', 0)
                lines.append('  ' + n + ': ' + format(c, '+.2f') + '%')
    except:
        pass
    lines.append('')
    try:
        stocks = scan_market()
        for s in stocks:
            s['score'] = score_stock(s)
        stocks.sort(key=lambda x: abs(x.get('change_pct', 0)), reverse=True)
        gainers = [s for s in stocks if s['change_pct'] > 0][:3]
        losers = [s for s in stocks if s['change_pct'] < 0][:3]
        if gainers:
            lines.append('Top Gainers:')
            for s in gainers:
                lines.append('  ' + s['name'] + '(' + s['code'] + ') +' + str(round(s['change_pct'],1)) + '% Score:' + str(s['score']))
        if losers:
            lines.append('')
            lines.append('Top Losers:')
            for s in losers:
                lines.append('  ' + s['name'] + '(' + s['code'] + ') ' + str(round(s['change_pct'],1)) + '% Score:' + str(s['score']))
    except:
        pass
    lines.append('')
    lines.append('Tomorrow: --daily for morning scan')
    return NL.join(lines)

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'morning'
    if mode == 'morning':
        print(morning_report())
    elif mode == 'evening':
        print(evening_report())
    else:
        print('Usage: python daily_report.py [morning|evening]')