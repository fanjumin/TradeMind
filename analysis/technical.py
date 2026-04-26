import pandas as pd


def get_trend(df):
    """Comprehensive trend judgment based on MA alignment"""
    if df.empty or 'close' not in df.columns:
        return 'neutral'
    
    close = df['close'].iloc[-1]
    ma5 = df.get('MA5', pd.Series([0]*len(df))).iloc[-1]
    ma10 = df.get('MA10', pd.Series([0]*len(df))).iloc[-1]
    ma20 = df.get('MA20', pd.Series([0]*len(df))).iloc[-1]
    ma60 = df.get('MA60', pd.Series([0]*len(df))).iloc[-1]
    
    signals = 0
    if ma5 > 0 and close > ma5: signals += 1
    if ma10 > 0 and close > ma10: signals += 1
    if ma20 > 0 and close > ma20: signals += 1
    if ma60 > 0 and close > ma60: signals += 1
    if ma5 > 0 and ma20 > 0 and ma5 > ma20: signals += 1
    
    if signals >= 4: return 'strong_uptrend'
    elif signals >= 3: return 'uptrend'
    elif signals >= 2: return 'neutral'
    else: return 'downtrend'


def get_trend_detail(df):
    """Return detailed trend information"""
    if df.empty:
        return {}
    
    close = df['close'].iloc[-1]
    prev = df['close'].iloc[-2] if len(df) > 1 else close
    change = close - prev
    pct = (change / prev) * 100 if prev != 0 else 0
    
    ema12 = df['close'].ewm(span=12).mean().iloc[-1]
    ema26 = df['close'].ewm(span=26).mean().iloc[-1]
    macd = ema12 - ema26
    
    return {
        'close': float(close),
        'change': round(float(change), 2),
        'change_pct': round(float(pct), 2),
        'ma5': float(df.get('MA5', pd.Series([0]*len(df))).iloc[-1]),
        'ma10': float(df.get('MA10', pd.Series([0]*len(df))).iloc[-1]),
        'ma20': float(df.get('MA20', pd.Series([0]*len(df))).iloc[-1]),
        'ma60': float(df.get('MA60', pd.Series([0]*len(df))).iloc[-1]),
        'macd': round(float(macd), 2),
        'trend': get_trend(df),
    }
