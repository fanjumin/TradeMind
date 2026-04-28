"""
TradeMind Convertible Bond Data Module — 多资产支持
数据源: Eastmoney (列表) + Tencent qt (实时行情)
注意: Eastmoney 在这个环境中仅 datacenter 端点可用
"""
import os, json, time, urllib.request
from datetime import datetime
import pandas as pd

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'cb_cache')
os.makedirs(CACHE_DIR, exist_ok=True)
CB_LIST_CACHE = os.path.join(CACHE_DIR, 'cb_list.json')


def fetch_cb_list(force_refresh=False, active_only=True):
    """获取可转债列表。缓存 24 小时。
    Args:
        active_only: 仅返回未退市的可转债
    Returns list of {code, name, stock_code, stock_name, premium_rt, price, ...}
    """
    if not force_refresh and os.path.exists(CB_LIST_CACHE):
        mtime = os.path.getmtime(CB_LIST_CACHE)
        if time.time() - mtime < 86400:
            with open(CB_LIST_CACHE) as f:
                cached = json.load(f)
            if cached:
                return cached
    
    all_cbs = []
    today = datetime.now().strftime('%Y-%m-%d')
    
    try:
        # Fetch from Eastmoney
        for page in range(1, 6):  # First 5 pages = ~50 items, enough for active ones
            try:
                url = (f"http://datacenter.eastmoney.com/api/data/v1/get"
                       f"?reportName=RPT_BOND_CB_LIST&columns=ALL"
                       f"&pageNumber={page}&pageSize=20"
                       f"&sortTypes=-1&sortColumns=LISTING_DATE")
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                resp = urllib.request.urlopen(req, timeout=15)
                data = json.loads(resp.read())
                
                items = data.get('result', {}).get('data', [])
                if not items:
                    break
                
                for item in items:
                    delist_date = item.get('DELIST_DATE', '')
                    expire_date = item.get('EXPIRE_DATE', '')[:10] if item.get('EXPIRE_DATE') else ''
                    
                    # Skip delisted
                    if active_only and delist_date:
                        continue
                    # Skip expired
                    if active_only and expire_date and expire_date < today:
                        continue
                    
                    code = item.get('SECURITY_CODE', '')
                    name = item.get('SECURITY_NAME_ABBR', '')
                    stock_code = item.get('CONVERT_STOCK_CODE', '')
                    
                    # Determine market
                    secucode = item.get('SECUCODE', '')
                    market = 'sh' if '.SH' in secucode else 'sz'
                    
                    all_cbs.append({
                        'code': code,
                        'name': name,
                        'market': market,
                        'stock_code': stock_code,
                        'listing_date': (item.get('LISTING_DATE', '') or '')[:10],
                        'expire_date': expire_date,
                        'rating': item.get('RATING', ''),
                        'asset_class': 'cb',
                    })
            except Exception as e:
                continue
        
        # Deduplicate
        seen = set()
        unique = []
        for cb in all_cbs:
            if cb['code'] not in seen:
                seen.add(cb['code'])
                unique.append(cb)
        
        # Cache
        with open(CB_LIST_CACHE, 'w') as f:
            json.dump(unique, f, ensure_ascii=False)
        
        return unique
    except Exception as e:
        print(f"[CB] fetch_cb_list error: {e}")
        # Return cached even if stale
        if os.path.exists(CB_LIST_CACHE):
            with open(CB_LIST_CACHE) as f:
                return json.load(f)
        return []


def get_cb_price(symbol):
    """获取可转债实时行情 (Tencent qt).
    symbol: 6-digit code like '110044'
    """
    code = str(symbol).zfill(6)
    if code.startswith(('1', '5')):
        qt_symbol = f'sh{code}'
    else:
        qt_symbol = f'sz{code}'
    
    try:
        url = f'http://qt.gtimg.cn/q={qt_symbol}'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read().decode('gbk', errors='replace')
        
        if 'none_match' in raw:
            return None
        
        parts = raw.split('~')
        if len(parts) < 5:
            return None
        
        return {
            'code': code,
            'name': parts[1],
            'price': float(parts[3]) if len(parts) > 3 else 0,
            'change': float(parts[4]) if len(parts) > 4 else 0,
            'change_pct': float(parts[5]) if len(parts) > 5 else 0,
            'volume': float(parts[6]) if len(parts) > 6 else 0,
            'turnover': float(parts[7]) if len(parts) > 7 else 0,
            'asset_class': 'cb',
        }
    except Exception as e:
        return None


def get_cb_history(symbol, days=252):
    """获取可转债历史K线 (baostock)."""
    code = str(symbol).zfill(6)
    if code.startswith(('1', '5')):
        bs_code = f'sh.{code}'
    else:
        bs_code = f'sz.{code}'
    
    cache_file = os.path.join(CACHE_DIR, f'{code}.csv')
    if os.path.exists(cache_file):
        try:
            df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
            if len(df) >= days * 0.8:
                return df.tail(days)
        except:
            pass
    
    try:
        import baostock as bs
        from datetime import timedelta
        bs.login()
        start_date = (datetime.now() - timedelta(days=days*2)).strftime('%Y-%m-%d')
        
        rs = bs.query_history_k_data_plus(
            bs_code,
            'date,open,high,low,close,volume',
            start_date=start_date,
            frequency='d',
            adjustflag='2'
        )
        
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        bs.logout()
        
        if not rows:
            return None
        
        data = []
        for r in rows:
            data.append({
                'date': r[0],
                'open': float(r[1]),
                'high': float(r[2]),
                'low': float(r[3]),
                'close': float(r[4]),
                'volume': float(r[5]),
            })
        
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df.to_csv(cache_file)
        return df.tail(days)
    except Exception as e:
        print(f"[CB] history error for {symbol}: {e}")
        return None


# Quick lookup by name/code
def search_cb(query, limit=20):
    cbs = fetch_cb_list()
    q = query.lower()
    results = []
    for cb in cbs:
        if q in cb['name'].lower() or q in cb['code'] or q in cb.get('stock_code', ''):
            results.append(cb)
            if len(results) >= limit:
                break
    return results


# CLI
if __name__ == '__main__':
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'list'
    
    if cmd == 'list':
        cbs = fetch_cb_list()
        print(f"\n可转债总数: {len(cbs)} (活跃)")
        for cb in cbs[:20]:
            print(f"  {cb['code']} {cb['name']} -> {cb['stock_code']} | {cb.get('rating','?')} | {cb.get('expire_date','?')}")
    
    elif cmd == 'price':
        symbol = sys.argv[2] if len(sys.argv) > 2 else '110044'
        p = get_cb_price(symbol)
        if p:
            print(f"\n{p['code']} {p['name']}")
            print(f"  价格: {p['price']}  涨跌: {p['change_pct']:+.2f}%")
        else:
            print(f"未找到 {symbol}")
    
    elif cmd == 'search':
        q = sys.argv[2] if len(sys.argv) > 2 else '转债'
        results = search_cb(q)
        print(f"\n搜索 '{q}': {len(results)} 结果")
        for r in results[:10]:
            print(f"  {r['code']} {r['name']} -> {r['stock_code']}")
    
    else:
        print("Usage: python convertible.py [list|price <code>|search <kw>]")
