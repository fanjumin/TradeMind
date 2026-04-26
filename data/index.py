from data.price import get_index_price_data, get_latest_price as _get_latest_price_single
import requests


INDEX_CODES = {
    '上证指数': '000001',
    '深证成指': '399001',
    '创业板指': '399006',
    '科创50': '000688',
    '沪深300': '000300',
    '中证500': '000905',
}


def get_all_indices_status():
    """Get all major indices real-time status"""
    # Build batch query for Tencent
    codes = list(INDEX_CODES.values())
    symbols = []
    for code in codes:
        if code.startswith('000') or code.startswith('880'):
            symbols.append('sh' + code)
        else:
            symbols.append('sz' + code)
    
    url = "http://qt.gtimg.cn/q=" + ",".join(symbols)
    r = requests.get(url, timeout=5)
    
    results = {}
    lines = r.text.strip().rstrip(';').split(';')
    
    idx_names = list(INDEX_CODES.keys())
    for i, line in enumerate(lines):
        if '~' not in line:
            continue
        parts = line.split('~')
        if len(parts) < 45:
            continue
        
        name = idx_names[i] if i < len(idx_names) else 'Unknown'
        results[name] = {
            'code': codes[i] if i < len(codes) else '',
            'name': parts[1],
            'close': float(parts[3]),
            'change': float(parts[31]),
            'change_pct': float(parts[32]),
            'high': float(parts[33]),
            'low': float(parts[34]),
            'amount': float(parts[37]) if len(parts) > 37 and parts[37] else 0,
        }
    
    # Get K-line for MA data
    for name, code in INDEX_CODES.items():
        if name in results:
            try:
                df = get_index_price_data(code, datalen=60)
                if not df.empty:
                    results[name]['ma5'] = float(df['MA5'].iloc[-1])
                    results[name]['ma20'] = float(df['MA20'].iloc[-1])
                    results[name]['ma60'] = float(df['MA60'].iloc[-1])
            except:
                results[name]['ma5'] = 0
                results[name]['ma20'] = 0
                results[name]['ma60'] = 0
    
    return results
