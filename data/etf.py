"""
TradeMind ETF Data Module — 多资产支持
数据源: baostock (列表+历史) + Tencent qt (实时行情)
"""
import os, json, time
import urllib.request
from datetime import datetime
import pandas as pd

# Cache
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'etf_cache')
os.makedirs(CACHE_DIR, exist_ok=True)
ETF_LIST_CACHE = os.path.join(CACHE_DIR, 'etf_list.json')

# ============================================================
# ETF List
# ============================================================

def fetch_etf_list(force_refresh=False):
    """获取全市场 ETF 列表，缓存 24 小时。
    Returns list of {code, name, market, type}
    """
    # Check cache
    if not force_refresh and os.path.exists(ETF_LIST_CACHE):
        mtime = os.path.getmtime(ETF_LIST_CACHE)
        if time.time() - mtime < 86400:  # 24h
            with open(ETF_LIST_CACHE) as f:
                cached = json.load(f)
            if cached:
                return cached
    
    try:
        import baostock as bs
        bs.login()
        rs = bs.query_stock_basic(code_name="ETF")
        etfs = []
        while rs.next():
            row = rs.get_row_data()
            code_full = row[0]  # e.g., sh.510050
            name = row[1]
            
            # Extract market and code
            market = code_full[:2]  # sh or sz
            code = code_full[3:]     # 510050
            
            etfs.append({
                'code': code,
                'code_full': code_full,
                'name': name,
                'market': market,
                'asset_class': 'etf',
            })
        bs.logout()
        
        # Add type classification
        _classify_etfs(etfs)
        
        # Cache
        with open(ETF_LIST_CACHE, 'w') as f:
            json.dump(etfs, f, ensure_ascii=False)
        
        return etfs
    except Exception as e:
        print(f"[ETF] fetch_etf_list error: {e}")
        return []


def _classify_etfs(etfs):
    """Classify ETFs by name patterns."""
    for e in etfs:
        name = e['name']
        if '货币' in name:
            e['etf_type'] = '货币'
        elif '债' in name:
            e['etf_type'] = '债券'
        elif '黄金' in name or '金' in name:
            e['etf_type'] = '黄金'
        elif '科创' in name:
            e['etf_type'] = '股票-科创'
        elif '创业' in name:
            e['etf_type'] = '股票-创业'
        elif '50' in name:
            e['etf_type'] = '股票-大盘'
        elif '300' in name:
            e['etf_type'] = '股票-大盘'
        elif '500' in name:
            e['etf_type'] = '股票-中盘'
        elif '1000' in name:
            e['etf_type'] = '股票-小盘'
        elif '行业' in name or '产业' in name:
            e['etf_type'] = '股票-行业'
        else:
            e['etf_type'] = '股票-其他'


# ============================================================
# ETF Price (Real-time)
# ============================================================

def get_etf_price(symbol):
    """Get ETF real-time quote from Tencent qt.
    Returns dict: {code, name, price, change, change_pct, volume, turnover, pe}
    """
    code = str(symbol).zfill(6)
    if code.startswith(('6', '5')):
        qt_symbol = f's_sh{code}'
    else:
        qt_symbol = f's_sz{code}'
    
    try:
        url = f'http://qt.gtimg.cn/q={qt_symbol}'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read().decode('gbk', errors='replace')
        
        if 'none_match' in raw or '="";' in raw:
            return None
        
        # Parse: v_s_sh510050="1~name~code~price~change~change_pct~volume~turnover~...~PE~..."
        parts = raw.split('~')
        if len(parts) < 10:
            return None
        
        return {
            'code': code,
            'name': parts[1] if len(parts) > 1 else '',
            'price': float(parts[3]) if len(parts) > 3 else 0,
            'change': float(parts[4]) if len(parts) > 4 else 0,
            'change_pct': float(parts[5]) if len(parts) > 5 else 0,
            'volume': int(float(parts[6])) if len(parts) > 6 else 0,
            'turnover': float(parts[7]) if len(parts) > 7 else 0,
            'pe': float(parts[9]) if len(parts) > 9 and parts[9] else 0,
            'asset_class': 'etf',
        }
    except Exception as e:
        return None


# ============================================================
# ETF History (K-line)
# ============================================================

def get_etf_history(symbol, days=252):
    """Get ETF historical K-line data from baostock.
    Returns pandas DataFrame with columns: open, high, low, close, volume
    """
    code = str(symbol).zfill(6)
    if code.startswith(('6', '5')):
        bs_code = f'sh.{code}'
    else:
        bs_code = f'sz.{code}'
    
    # Check local cache
    cache_file = os.path.join(CACHE_DIR, f'{code}.csv')
    if os.path.exists(cache_file):
        mtime = os.path.getmtime(cache_file)
        # Cache valid for today
        cache_date = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
        today = datetime.now().strftime('%Y-%m-%d')
        if cache_date == today:
            try:
                df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
                if len(df) >= days * 0.8:
                    return df.tail(days)
            except:
                pass
    
    try:
        import baostock as bs
        bs.login()
        
        # Calculate start date
        from datetime import timedelta
        start_date = (datetime.now() - timedelta(days=days*2)).strftime('%Y-%m-%d')
        
        rs = bs.query_history_k_data_plus(
            bs_code,
            'date,open,high,low,close,volume',
            start_date=start_date,
            frequency='d',
            adjustflag='2'  # 前复权
        )
        
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        bs.logout()
        
        if not rows:
            return None
        
        # Convert to DataFrame
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
        
        # Cache
        df.to_csv(cache_file)
        
        return df.tail(days)
    except Exception as e:
        print(f"[ETF] get_etf_history error for {symbol}: {e}")
        return None


# ============================================================
# Bulk Operations
# ============================================================

def get_etf_prices(symbols, max_workers=10):
    """Get prices for multiple ETFs using batch Tencent query."""
    results = {}
    # Tencent supports batch: s_sh510050,s_sz159915,...
    batch = []
    for s in symbols:
        code = str(s).zfill(6)
        if code.startswith(('6', '5')):
            batch.append(f's_sh{code}')
        else:
            batch.append(f's_sz{code}')
    
    if not batch:
        return results
    
    # Process in chunks of 50
    for i in range(0, len(batch), 50):
        chunk = batch[i:i+50]
        qt_str = ','.join(chunk)
        try:
            url = f'http://qt.gtimg.cn/q={qt_str}'
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            resp = urllib.request.urlopen(req, timeout=15)
            raw = resp.read().decode('gbk', errors='replace')
            
            for line in raw.split(';'):
                if '~' not in line:
                    continue
                parts = line.split('~')
                if len(parts) < 6:
                    continue
                # Extract code from v_s_shXXXXXX
                code_match = line.split('="')[0]
                code = code_match.replace('v_s_sh', '').replace('v_s_sz', '')
                results[code] = {
                    'code': code,
                    'name': parts[1],
                    'price': float(parts[3]) if len(parts) > 3 else 0,
                    'change_pct': float(parts[5]) if len(parts) > 5 else 0,
                    'volume': float(parts[6]) if len(parts) > 6 else 0,
                }
        except Exception as e:
            print(f"[ETF] batch error: {e}")
    
    return results


def search_etfs(query, limit=20):
    """Search ETFs by name or code."""
    etfs = fetch_etf_list()
    query_lower = query.lower()
    results = []
    
    for e in etfs:
        if query_lower in e['name'].lower() or query_lower in e['code']:
            results.append(e)
            if len(results) >= limit:
                break
    
    return results


def get_popular_etfs():
    """Return list of popular/major ETFs."""
    popular_codes = [
        '510050', '510300', '510500', '510880', '510900',
        '159915', '159919', '159949', '159941',
        '588000', '588080', '513100', '513500',
        '511880', '511010', '518880',
    ]
    
    etfs = fetch_etf_list()
    etf_map = {e['code']: e for e in etfs}
    
    result = []
    for code in popular_codes:
        if code in etf_map:
            result.append(etf_map[code])
    
    return result


# CLI
if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        
        if cmd == 'list':
            etfs = fetch_etf_list()
            print(f"\nETF 总数: {len(etfs)}")
            # Show by type
            types = {}
            for e in etfs:
                t = e.get('etf_type', '其他')
                types[t] = types.get(t, 0) + 1
            for t, c in sorted(types.items()):
                print(f"  {t}: {c} 只")
            
            print(f"\n热门 ETF:")
            for e in get_popular_etfs()[:15]:
                print(f"  {e['code']} {e['name']} [{e.get('etf_type','?')}]")
        
        elif cmd == 'price':
            symbol = sys.argv[2] if len(sys.argv) > 2 else '510050'
            p = get_etf_price(symbol)
            if p:
                print(f"\n{p['code']} {p['name']}")
                print(f"  价格: {p['price']}  涨跌: {p['change_pct']:+.2f}%")
                print(f"  成交量: {p['volume']}  成交额: {p['turnover']:.0f}")
            else:
                print(f"未找到 {symbol}")
        
        elif cmd == 'search':
            query = sys.argv[2] if len(sys.argv) > 2 else '科创'
            results = search_etfs(query)
            print(f"\n搜索 '{query}': {len(results)} 结果")
            for r in results[:10]:
                print(f"  {r['code']} {r['name']} [{r.get('etf_type','?')}]")
        
        elif cmd == 'history':
            symbol = sys.argv[2] if len(sys.argv) > 2 else '510050'
            df = get_etf_history(symbol, days=20)
            if df is not None:
                print(f"\n{symbol} 最近 20 天K线:")
                print(df.tail(5))
            else:
                print(f"无数据")
        
        else:
            print(f"Usage: python etf.py [list|price <code>|search <kw>|history <code>]")
    else:
        print(f"Usage: python etf.py [list|price <code>|search <kw>|history <code>]")
