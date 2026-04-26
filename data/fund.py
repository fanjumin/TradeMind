import requests


def _get_sina_symbol(symbol):
    clean = symbol.replace('.SZ', '').replace('.SH', '').replace('.BJ', '')
    if clean.startswith('6'):
        return 'sh' + clean
    elif clean.startswith(('0', '3')):
        return 'sz' + clean
    else:
        return 'bj' + clean


def get_fund_flow(symbol, days=5):
    """Get trading volume and amount as flow proxy"""
    sina_symbol = _get_sina_symbol(symbol)
    url = "http://qt.gtimg.cn/q=" + sina_symbol
    r = requests.get(url, timeout=5)
    text = r.text.strip().strip(';')
    if '~' not in text:
        return 0, {}
    parts = text.split('~')
    if len(parts) < 40:
        return 0, {}
    
    volume = float(parts[6]) if parts[6] else 0
    amount = float(parts[37]) if len(parts) > 37 and parts[37] else 0
    change_pct = float(parts[32]) if len(parts) > 32 else 0
    
    # Simple flow proxy: positive change + high volume = positive flow
    flow_proxy = change_pct * volume / 1e6
    
    return flow_proxy, {
        'volume': volume,
        'amount': amount,
        'change_pct': change_pct,
    }
