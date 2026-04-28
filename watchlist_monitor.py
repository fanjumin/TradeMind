#!/usr/bin/env python3
# TradeMind Watchlist Monitor - track your stocks
import sys, os, json, time
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'watchlist.json')

DEFAULT_WATCHLIST = ['600519','000858','601318','300750','000333']

def load_watchlist():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return DEFAULT_WATCHLIST

def save_watchlist(wl):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w') as f:
        json.dump(wl, f, ensure_ascii=False, indent=2)

def monitor():
    from data.price import get_latest_price
    wl = load_watchlist()
    results = []
    for code in wl:
        try:
            info = get_latest_price(code)
            if info and 'error' not in info:
                ch = info.get('change_pct', 0)
                if ch > 3: sig = 'STRONG_BUY'
                elif ch > 1: sig = 'BUY'
                elif ch > -1: sig = 'HOLD'
                elif ch > -3: sig = 'WATCH'
                else: sig = 'SELL'
                results.append({
                    'code': info.get('code',code),
                    'name': info.get('name',''),
                    'price': info.get('price',0),
                    'change_pct': ch,
                    'signal': sig,
                })
            time.sleep(0.1)
        except:
            pass
    return results

def fmt_monitor(results):
    emoji = {'STRONG_BUY': 'STRONG BUY', 'BUY': 'BUY', 'HOLD': 'HOLD', 'WATCH': 'WATCH', 'SELL': 'SELL'}
    lines = ['', '=' * 55, '  My Watchlist  ' + datetime.now().strftime('%H:%M'), '=' * 55, '']
    for r in results:
        s = r['signal']
        e = emoji.get(s, '?')
        lines.append('  [' + e + '] ' + r['name'] + '(' + r['code'] + ') ' + format(r['price'],'.2f') + ' ' + format(r['change_pct'],'+.2f') + '%')
    lines.append('')
    lines.append('-' * 55)
    return chr(10).join(lines)

def fmt_wechat(results):
    emoji = {'STRONG_BUY': 'STRONG BUY', 'BUY': 'BUY', 'HOLD': 'HOLD', 'WATCH': 'WATCH', 'SELL': 'SELL'}
    lines = ['Watchlist:']
    for r in results:
        s = r['signal']
        e = emoji.get(s, '?')
        lines.append(e + ' ' + r['name'] + ' ' + format(r['change_pct'],'+.2f') + '%')
    return chr(10).join(lines)

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'show'
    if cmd == 'show':
        r = monitor()
        print(fmt_monitor(r))
    elif cmd == 'add':
        sym = sys.argv[2]
        wl = load_watchlist()
        if sym not in wl:
            wl.append(sym)
            save_watchlist(wl)
            print('Added ' + sym)
        else:
            print(sym + ' already in watchlist')
    elif cmd == 'remove':
        sym = sys.argv[2]
        wl = load_watchlist()
        if sym in wl:
            wl.remove(sym)
            save_watchlist(wl)
            print('Removed ' + sym)
    elif cmd == 'list':
        wl = load_watchlist()
        print('Watchlist (' + str(len(wl)) + '): ' + ', '.join(wl))
    elif cmd == 'wechat':
        r = monitor()
        print(fmt_wechat(r))
    else:
        print('Usage: watchlist_monitor.py [show|add|remove|list|wechat]')