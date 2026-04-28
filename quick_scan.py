#!/usr/bin/env python3
"""Quick scanner for cronjob — scans watchlist only."""
import sys, os, json
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Small watchlist (50 major A-stocks)
WATCHLIST = [
    '600519','000858','000001','600036','601318','600276','000333','002594',
    '300750','600900','601166','002475','601012','002230','688981','002049',
    '300059','600030','000725','601899','600809','000568','600887','601088',
    '002415','600585','000651','601398','600028','601857','601728','600050',
    '000002','002714','601888','600031','601390','600048','601688','600837',
    '300015','002142','000063','000792','002236','300124','603259','688111',
    '601615','600570',
]

from data.price import get_latest_price
import time

def quick_scan():
    results = []
    for code in WATCHLIST:
        try:
            info = get_latest_price(code)
            if info and 'error' not in info:
                results.append({
                    'code': info.get('code', code),
                    'name': info.get('name', ''),
                    'price': info.get('price', 0),
                    'change_pct': info.get('change_pct', 0),
                    'pe': info.get('pe', 0),
                    'turnover': info.get('turnover', 0),
                })
            time.sleep(0.1)
        except:
            pass
    return results

def find_signals(stocks):
    """Find trading signals."""
    signals = []
    for s in stocks:
        change = s.get('change_pct', 0)
        pe = s.get('pe', 0)
        turnover = s.get('turnover', 0)
        
        if change > 5:
            signals.append({'type': 'surge', 'stock': s, 'msg': f"🚀 {s['name']} 大涨 {change:+.1f}%"})
        elif change < -5:
            signals.append({'type': 'plunge', 'stock': s, 'msg': f"📉 {s['name']} 大跌 {change:+.1f}%"})
        elif change > 3 and turnover > 3:
            signals.append({'type': 'active', 'stock': s, 'msg': f"📊 {s['name']} 放量上涨 {change:+.1f}% 换手{turnover:.1f}%"})
        if pe > 0 and pe < 15 and change > 0:
            signals.append({'type': 'value', 'stock': s, 'msg': f"💎 {s['name']} 低PE({pe:.0f}) + {change:+.1f}%"})
    
    return signals

if __name__ == '__main__':
    print(f"Quick scan: {len(WATCHLIST)} stocks @ {datetime.now().strftime('%H:%M:%S')}")
    stocks = quick_scan()
    signals = find_signals(stocks)
    
    # Top movers
    sorted_stocks = sorted(stocks, key=lambda x: abs(x.get('change_pct', 0)), reverse=True)
    
    lines = [f"📊 TradeMind实时扫描 {datetime.now().strftime('%H:%M')}"]
    lines.append(f"监控 {len(WATCHLIST)} 只 | 有效 {len(stocks)} 只\n")
    
    if signals:
        lines.append("🔔 信号:")
        for sig in signals[:8]:
            lines.append(f"  {sig['msg']}")
    else:
        lines.append("无异常信号")
    
    lines.append(f"\n📈 涨幅Top5:")
    for i, s in enumerate(sorted_stocks[:5], 1):
        c = s.get('change_pct', 0)
        lines.append(f"  {i}. {s['name']}({s['code']}) {c:+.1f}%")
    
    lines.append(f"\n📉 跌幅Top5:")
    for i, s in enumerate(sorted_stocks[-5:], 1):
        c = s.get('change_pct', 0)
        lines.append(f"  {i}. {s['name']}({s['code']}) {c:+.1f}%")
    
    msg = '\n'.join(lines)
    print(msg)
