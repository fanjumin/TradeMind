import pandas as pd
import numpy as np


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
    """Return detailed trend information with ALL indicators"""
    if df.empty:
        return {}

    close = df['close'].iloc[-1]
    prev = df['close'].iloc[-2] if len(df) > 1 else close
    change = close - prev
    pct = (change / prev) * 100 if prev != 0 else 0

    ema12 = df['close'].ewm(span=12).mean().iloc[-1]
    ema26 = df['close'].ewm(span=26).mean().iloc[-1]
    macd = ema12 - ema26

    result = {
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

    # RSI (Relative Strength Index)
    result.update(_calc_rsi(df))

    # KDJ
    result.update(_calc_kdj(df))

    # Bollinger Bands
    result.update(_calc_boll(df))

    # Support/Resistance
    result.update(_calc_support_resistance(df))

    # Volume-Price Analysis
    result.update(_calc_volume_price(df))

    return result


# ============================================================
# RSI - Relative Strength Index
# ============================================================
def _calc_rsi(df, period=14):
    """Calculate RSI. Returns dict with rsi_value and signal"""
    if len(df) < period + 1:
        return {'rsi': 50, 'rsi_signal': 'neutral'}

    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=period).mean().iloc[-1]
    avg_loss = loss.rolling(window=period).mean().iloc[-1]

    if avg_loss == 0:
        rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

    if rsi >= 80:
        signal = 'overbought'
    elif rsi >= 60:
        signal = 'strong'
    elif rsi >= 40:
        signal = 'neutral'
    elif rsi >= 20:
        signal = 'weak'
    else:
        signal = 'oversold'

    return {'rsi': round(float(rsi), 2), 'rsi_signal': signal}


# ============================================================
# KDJ - Stochastic Oscillator
# ============================================================
def _calc_kdj(df, period=9):
    """Calculate KDJ. Returns dict with k, d, j values and signal"""
    if len(df) < period:
        return {'k': 50, 'd': 50, 'j': 50, 'kdj_signal': 'neutral'}

    low_min = df['low'].rolling(window=period).min()
    high_max = df['high'].rolling(window=period).max()

    rsv = (df['close'] - low_min) / (high_max - low_min) * 100
    rsv = rsv.fillna(50)

    k = rsv.ewm(com=2).mean()
    d = k.ewm(com=2).mean()
    j = 3 * k - 2 * d

    k_val = float(k.iloc[-1])
    d_val = float(d.iloc[-1])
    j_val = float(j.iloc[-1])

    # KDJ signal
    if j_val >= 100:
        signal = 'overbought'
    elif j_val <= 0:
        signal = 'oversold'
    elif k_val > d_val and j_val > 50:
        signal = 'bullish'
    elif k_val < d_val and j_val < 50:
        signal = 'bearish'
    else:
        signal = 'neutral'

    return {
        'k': round(k_val, 2),
        'd': round(d_val, 2),
        'j': round(j_val, 2),
        'kdj_signal': signal,
    }


# ============================================================
# Bollinger Bands
# ============================================================
def _calc_boll(df, period=20, std_dev=2):
    """Calculate Bollinger Bands. Returns upper/mid/lower and position"""
    if len(df) < period:
        return {'boll_upper': 0, 'boll_mid': 0, 'boll_lower': 0, 'boll_position': 'neutral'}

    close = df['close']
    mid = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()

    upper = mid + std_dev * std
    lower = mid - std_dev * std

    upper_val = float(upper.iloc[-1])
    mid_val = float(mid.iloc[-1])
    lower_val = float(lower.iloc[-1])
    price = float(close.iloc[-1])

    # Position within bands (%B)
    if upper_val != lower_val:
        pct_b = (price - lower_val) / (upper_val - lower_val)
    else:
        pct_b = 0.5

    if pct_b >= 1.0:
        position = 'above_upper'
    elif pct_b >= 0.8:
        position = 'near_upper'
    elif pct_b >= 0.5:
        position = 'middle'
    elif pct_b >= 0.2:
        position = 'near_lower'
    else:
        position = 'below_lower'

    # Bandwidth (squeeze detection)
    bandwidth = (upper_val - lower_val) / mid_val * 100 if mid_val > 0 else 0

    return {
        'boll_upper': round(upper_val, 2),
        'boll_mid': round(mid_val, 2),
        'boll_lower': round(lower_val, 2),
        'boll_pct_b': round(float(pct_b), 3),
        'boll_width': round(float(bandwidth), 2),
        'boll_position': position,
    }


# ============================================================
# Support & Resistance Levels
# ============================================================
def _calc_support_resistance(df, lookback=20):
    """Calculate support/resistance from recent highs/lows and pivot points"""
    if len(df) < lookback:
        return {'resistance': 0, 'support': 0, 'pivot': 0}

    recent = df.tail(lookback)
    high = float(recent['high'].max())
    low = float(recent['low'].min())
    close = float(df['close'].iloc[-1])
    prev_close = float(df['close'].iloc[-2]) if len(df) > 1 else close
    prev_high = float(df['high'].iloc[-2]) if len(df) > 1 else high
    prev_low = float(df['low'].iloc[-2]) if len(df) > 1 else low

    # Classic pivot point
    pivot = (prev_high + prev_low + prev_close) / 3

    # Recent swing high/low as resistance/support
    resistance = high
    support = low

    # Distance to levels
    dist_to_res = (resistance - close) / close * 100
    dist_to_sup = (close - support) / close * 100

    return {
        'resistance': round(resistance, 2),
        'support': round(support, 2),
        'pivot': round(pivot, 2),
        'dist_to_res_pct': round(float(dist_to_res), 2),
        'dist_to_sup_pct': round(float(dist_to_sup), 2),
    }


# ============================================================
# Volume-Price Analysis
# ============================================================
def _calc_volume_price(df, period=20):
    """Volume-price relationship analysis"""
    if len(df) < period or 'volume' not in df.columns:
        return {'vol_trend': 'neutral', 'vol_ratio': 1.0, 'vol_price_signal': 'neutral'}

    volume = df['volume']
    close = df['close']

    # Volume trend: compare recent 5-day avg to 20-day avg
    vol_ma5 = volume.tail(5).mean()
    vol_ma20 = volume.tail(period).mean()

    vol_ratio = vol_ma5 / vol_ma20 if vol_ma20 > 0 else 1.0

    # Price trend
    price_change = close.iloc[-1] / close.iloc[-5] - 1 if len(close) >= 5 else 0

    # Volume-price signals
    if price_change > 0.02 and vol_ratio > 1.5:
        signal = 'strong_uptrend'  # 放量上涨
    elif price_change > 0.02 and vol_ratio < 0.8:
        signal = 'weak_uptrend'  # 缩量上涨
    elif price_change < -0.02 and vol_ratio > 1.5:
        signal = 'strong_downtrend'  # 放量下跌
    elif price_change < -0.02 and vol_ratio < 0.8:
        signal = 'weak_downtrend'  # 缩量下跌
    elif vol_ratio > 2.0:
        signal = 'volume_surge'  # 放量异动
    elif vol_ratio < 0.5:
        signal = 'volume_shrink'  # 缩量整理
    else:
        signal = 'neutral'

    # Volume trend direction
    if vol_ma5 > vol_ma20 * 1.2:
        vol_trend = 'increasing'
    elif vol_ma5 < vol_ma20 * 0.8:
        vol_trend = 'decreasing'
    else:
        vol_trend = 'stable'

    return {
        'vol_trend': vol_trend,
        'vol_ratio': round(float(vol_ratio), 2),
        'vol_price_signal': signal,
        'vol_ma5': round(float(vol_ma5), 0),
        'vol_ma20': round(float(vol_ma20), 0),
    }
