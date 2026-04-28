#!/usr/bin/env python3
# TradeMind Market Scanner Engine - retail investor focused
# Full market scan -> multi-dim scoring -> human-readable picks
import sys, os, json, time
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data.price import get_latest_price

SCAN_POOL = [
    '600519','000858','000568','002304','600809','000596','601318','600036',
    '000001','601166','600030','601688','601398','002415','002230','300750',
    '002049','688981','002594','300059','002236','300124','002475','002371',
    '601012','300274','600900','601615','600276','300015','300760','000002',
    '600048','601668','601390','600585','000725','002714','000651','000333',
    '600690','601899','600028','601857','000792','601088','601728','600050',
    '002281','688036','600588','002410','601919','600809','600887','002142',
    '601888','600031','603259','688111','688012','688599','002129','000063',
    '300413','002352','601166','600570','002460','300014','603993','688008',
    '002916','300408','688126','301269','600150','002230','601390','600050',
    '600104','002241','601186','601800','600115','000100','600703','002456',
    '300760','603986','002049','601066','600196','000538','603288','688005',
    '510050','510300','510500','159915','588000','513100','513500','159919',
]

def scan_market():
    results = []
    for i, code in enumerate(SCAN_POOL):
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
                    'volume_ratio': info.get('volume_ratio', 1.0),
                    'amplitude': info.get('amplitude', 0),
                })
            if i % 30 == 0 and i > 0:
                time.sleep(0.3)
        except:
            pass
    return results

def score_stock(s):
    score = 50
    c = s.get('change_pct', 0)
    if c > 5: score += 40
    elif c > 3: score += 30
    elif c > 1: score += 20
    elif c > 0: score += 10
    elif c > -1: score += 5
    elif c > -3: score -= 5
    elif c > -5: score -= 10
    else: score -= 20
    pe = s.get('pe', 0)
    if 0 < pe < 15: score += 25
    elif 15 <= pe < 25: score += 20
    elif 25 <= pe < 40: score += 10
    elif pe >= 80: score -= 10
    vr = s.get('volume_ratio', 1.0)
    if vr > 3: score += 20
    elif vr > 2: score += 15
    elif vr > 1.5: score += 10
    elif vr > 1: score += 5
    amp = s.get('amplitude', 0)
    if 0 < amp < 3: score += 15
    elif 3 <= amp < 5: score += 10
    elif 5 <= amp < 8: score += 5
    return min(100, max(0, score))

def classify(s):
    c, pe, vr, amp = s.get('change_pct',0), s.get('pe',0), s.get('volume_ratio',1), s.get('amplitude',0)
    sigs = []
    if c > 5 and vr > 2: sigs.append(('Strong Breakout', 'FIRE'))
    elif c > 3: sigs.append(('Volume Rally', 'CHART'))
    elif c > 1: sigs.append(('Modest Rise', 'UP'))
    elif c > 0: sigs.append(('Slight Gain', 'RIGHT'))
    elif c > -1: sigs.append(('Narrow Range', 'DASH'))
    elif c > -3: sigs.append(('Pullback', 'DOWN'))
    else: sigs.append(('Sharp Drop', 'WARN'))
    if 0 < pe < 15: sigs.append(('Deep Value', 'GEM'))
    elif 0 < pe < 25: sigs.append(('Fair Value', 'CHECK'))
    elif pe > 80: sigs.append(('High PE', 'ALERT'))
    if vr > 3: sigs.append(('Explosive Vol', 'BOOM'))
    elif vr > 2: sigs.append(('High Volume', 'VOLUME'))
    if amp > 8: sigs.append(('Wild Swing', 'WAVE'))
    return sigs

def daily_picks(top_n=8):
    print(f"Scanning {len(SCAN_POOL)} stocks...", end=' ', flush=True)
    stocks = scan_market()
    print(f"got {len(stocks)} valid")
    for s in stocks:
        s['score'] = score_stock(s)
        s['signals'] = classify(s)
    stocks.sort(key=lambda x: x['score'], reverse=True)
    return {'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M'), 'total_scanned': len(stocks), 'picks': stocks[:top_n]}

def fmt(result):
    out = ["", "=" * 58, f"  TradeMind Market Scanner  {result['scan_time']}", "=" * 58]
    for i, s in enumerate(result['picks'], 1):
        n, code, pr, ch, pe, sc = s.get('name','?'), s['code'], s['price'], s['change_pct'], s['pe'], s['score']
        sigs = s.get('signals', [])
        bar = '#' * (sc // 10) + '-' * (10 - sc // 10)
        out.append(f"")
        out.append(f"  #{i}  {n} ({code})")
        out.append(f"      Price {pr:.2f}  |  {ch:+.2f}%  |  PE {pe:.1f}")
        out.append(f"      Score [{bar}] {sc}/100")
        out.append(f"      Signal: {' | '.join(t for t,_ in sigs[:4])}")
    out.extend(["", "-" * 58, f"  Scanned {result['total_scanned']} stocks", "=" * 58, ""])
    return chr(10).join(out)

def fmt_wechat(result):
    lines = [f"TradeMind ({result['scan_time']})", ""]
    for i, s in enumerate(result['picks'][:6], 1):
        lines.append(f"{i}. {s['name']}({s['code']}) {s['change_pct']:+.1f}% Score:{s['score']}")
    return chr(10).join(lines)

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--top', type=int, default=8)
    p.add_argument('--json', action='store_true')
    p.add_argument('--wechat', action='store_true')
    args = p.parse_args()
    result = daily_picks(top_n=args.top)
    if args.json: print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.wechat: print(fmt_wechat(result))
    else: print(fmt(result))
