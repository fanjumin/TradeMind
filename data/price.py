import requests
import time
import json
import pandas as pd
from datetime import datetime


def _get_sina_symbol(symbol):
    """Convert stock code to Sina format (e.g., 000001 -> sz000001)"""
    clean = symbol.replace('.SZ', '').replace('.SH', '').replace('.BJ', '')
    if clean.startswith('6'):
        return 'sh' + clean
    elif clean.startswith(('0', '3')):
        return 'sz' + clean
    elif clean.startswith(('8', '4')):
        return 'bj' + clean
    else:
        return 'sz' + clean


def _get_index_sina_symbol(index_code):
    """Convert index code to Sina format"""
    if index_code.startswith('000') or index_code.startswith('880'):
        return 'sh' + index_code
    else:
        return 'sz' + index_code


def get_price_data(symbol, period="daily", datalen=100):
    """Get historical K-line data from Sina Finance"""
    sina_symbol = _get_sina_symbol(symbol)
    
    url = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
    params = {
        "symbol": sina_symbol,
        "scale": "240",  # daily
        "ma": "no",
        "datalen": str(datalen),
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.sina.com.cn/",
    }
    
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=10)
            break
        except requests.exceptions.Timeout:
            if attempt < 2:
                time.sleep(1)
                continue
            raise
    data = json.loads(r.text)
    
    if not data:
        return pd.DataFrame()
    
    df = pd.DataFrame(data)
    df['date'] = pd.to_datetime(df['day'])
    df.set_index('date', inplace=True)
    df['close'] = df['close'].astype(float)
    df['open'] = df['open'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['volume'] = df['volume'].astype(float)
    
    # Calculate moving averages
    for w in [5, 10, 20, 60]:
        df['MA' + str(w)] = df['close'].rolling(window=w).mean()
    
    return df


def get_index_price_data(index_code, datalen=100):
    """Get index historical K-line data"""
    sina_symbol = _get_index_sina_symbol(index_code)
    
    url = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
    params = {
        "symbol": sina_symbol,
        "scale": "240",
        "ma": "no",
        "datalen": str(datalen),
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.sina.com.cn/",
    }
    
    r = requests.get(url, params=params, headers=headers, timeout=10)
    data = json.loads(r.text)
    
    if not data:
        return pd.DataFrame()
    
    df = pd.DataFrame(data)
    df['date'] = pd.to_datetime(df['day'])
    df.set_index('date', inplace=True)
    df['close'] = df['close'].astype(float)
    df['open'] = df['open'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['volume'] = df['volume'].astype(float)
    
    for w in [5, 10, 20, 60]:
        df['MA' + str(w)] = df['close'].rolling(window=w).mean()
    
    return df


def get_latest_price(symbol):
    """Get real-time price from Tencent Finance"""
    sina_symbol = _get_sina_symbol(symbol)
    url = "http://qt.gtimg.cn/q=" + sina_symbol
    
    r = requests.get(url, timeout=5)
    text = r.text.strip().strip(';')
    
    if '~' not in text:
        return None
    
    parts = text.split('~')
    
    if len(parts) < 45:
        return None
    
    return {
        'name': parts[1],
        'code': parts[2],
        'price': float(parts[3]),
        'prev_close': float(parts[4]),
        'open': float(parts[5]),
        'volume': float(parts[6]) if parts[6] else 0,
        'change': float(parts[31]),
        'change_pct': float(parts[32]),
        'high': float(parts[33]),
        'low': float(parts[34]),
        'amount': float(parts[37]) if len(parts) > 37 and parts[37] else 0,
    }
