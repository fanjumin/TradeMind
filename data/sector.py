import requests
import json


def get_top_sectors(top_n=10):
    """Get top gaining/losing sectors from Sina concept list"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.sina.com.cn/",
    }
    
    # Sina sector/concept real-time quote via qt.gtimg.cn
    # Board codes: bk = concept board
    # We will fetch from eastmoney push API instead
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1",
        "pz": str(top_n * 2),
        "po": "1",
        "np": "1",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": "m:90+t:2+f:!50",
        "fields": "f2,f3,f4,f12,f14",
    }
    headers2 = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }
    
    try:
        r = requests.get(url, params=params, headers=headers2, timeout=10)
        data = json.loads(r.text)
        if data.get('data') and data['data'].get('diff'):
            items = data['data']['diff']
            sorted_items = sorted(items, key=lambda x: float(x.get('f3', 0)), reverse=True)
            gainers = [{'name': x['f14'], 'change_pct': float(x['f3'])} for x in sorted_items[:top_n]]
            losers = [{'name': x['f14'], 'change_pct': float(x['f3'])} for x in sorted_items[-top_n:]]
            return gainers, losers
    except:
        pass
    
    # Fallback: return empty
    return [], []
