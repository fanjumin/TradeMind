#!/usr/bin/env python3
# TradeMind Retail Alerts - 5 simple signal types for retail investors
import sys, os, json, time
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SIGNAL_PRESETS = {
    'breakout': {
        'name': 'Breakout Surge',
        'desc': 'Price up 3%+ with volume 2x normal',
        'check': lambda s: s.get('change_pct',0) > 3 and s.get('volume_ratio',1) > 2,
    },
    'dip_buy': {
        'name': 'Dip Buying Opportunity',
        'desc': 'Price down 3%+ but PE under 25 (oversold quality)',
        'check': lambda s: s.get('change_pct',0) < -3 and 0 < s.get('pe',999) < 25,
    },
    'limit_up': {
        'name': 'Limit Up',
        'desc': 'Stock hit daily limit up (9.5%+)',
        'check': lambda s: s.get('change_pct',0) >= 9.5,
    },
    'volume_surge': {
        'name': 'Volume Explosion',
        'desc': 'Volume 5x+ normal with price up',
        'check': lambda s: s.get('volume_ratio',1) > 5 and s.get('change_pct',0) > 0,
    },
    'deep_value': {
        'name': 'Deep Value Find',
        'desc': 'PE under 10 with price stable or rising',
        'check': lambda s: 0 < s.get('pe',999) < 10 and s.get('change_pct',0) > -1,
    },
}

SCAN_POOL = [
    '600519','000858','601318','600036','000001','601166','002415','300750',
    '600276','601012','000333','002594','600900','600030','600585','601899',
    '601728','600050','002230','000725','002714','600809','601888','600031',
    '688981','002049','688111','603259','510050','510300','510500','159915',
]

def scan_alerts():
    from data.price import get_latest_price
    results = []
    for code in SCAN_POOL:
        try:
            info = get_latest_price(code)
            if info and 'error' not in info:
                results.append({
                    'code': info.get('code', code),
                    'name': info.get('name', ''),
                    'price': info.get('price', 0),
                    'change_pct': info.get('change_pct', 0),
                    'pe': info.get('pe', 0),
                    'volume_ratio': info.get('volume_ratio', 1.0),
                })
            time.sleep(0.1)
        except:
            pass
    
    alerts = []
    for s in results:
        for key, preset in SIGNAL_PRESETS.items():
            if preset['check'](s):
                alerts.append({
                    'type': key,
                    'name': preset['name'],
                    'stock': s,
                })
    return alerts

def fmt_alerts(alerts):
    if not alerts:
        return 'No alerts triggered'
    lines = ['', '=' * 50, '  TradeMind Alerts  ' + datetime.now().strftime('%H:%M'), '=' * 50, '']
    for a in alerts:
        s = a['stock']
        lines.append('  [' + a['name'] + '] ' + s['name'] + '(' + s['code'] + ') ' + format(s['price'],'.2f') + ' ' + format(s['change_pct'],'+.2f') + '%')
    lines.append('')
    return chr(10).join(lines)

def fmt_wechat(alerts):
    if not alerts:
        return 'No alerts'
    lines = ['Alerts:']
    for a in alerts[:5]:
        s = a['stock']
        lines.append(a['name'] + ': ' + s['name'] + ' ' + format(s['change_pct'],'+.2f') + '%')
    return chr(10).join(lines)

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'scan'
    if cmd == 'scan':
        print(fmt_alerts(scan_alerts()))
    elif cmd == 'wechat':
        print(fmt_wechat(scan_alerts()))
    elif cmd == 'list':
        for k, v in SIGNAL_PRESETS.items():
            print(k + ': ' + v['name'] + ' - ' + v['desc'])
    else:
        print('Usage: retail_alerts.py [scan|wechat|list]')