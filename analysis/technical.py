"""
Technical Analysis module for TradeMind.
Provides 25+ technical indicators for Chinese A-share market analysis.
Maintains backward compatibility with existing get_trend_detail() API.
"""
import pandas as pd
import numpy as np


# ============================================================
# MA / Trend
# ============================================================

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


def _calc_ma_deviation(df):
    """乖离率 BIAS — deviation from MA"""
    close = df['close']
    result = {}
    for p in [5, 10, 20, 60]:
        ma = close.rolling(window=p).mean()
        if len(ma.dropna()) > 0:
            bias = (close.iloc[-1] - ma.iloc[-1]) / ma.iloc[-1] * 100
            result[f'bias_ma{p}'] = round(float(bias), 2)
    return result


# ============================================================
# MACD
# ============================================================

def _calc_macd(df, fast=12, slow=26, signal=9):
    """MACD with histogram and divergence detection"""
    if len(df) < slow + signal:
        return {'macd_dif': 0, 'macd_dea': 0, 'macd_hist': 0, 'macd_signal': 'neutral'}

    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = 2 * (dif - dea)

    dif_val = float(dif.iloc[-1])
    dea_val = float(dea.iloc[-1])
    hist_val = float(hist.iloc[-1])

    # Signal
    prev_hist = float(hist.iloc[-2]) if len(hist) > 1 else 0
    if dif_val > dea_val and hist_val > 0 and hist_val < prev_hist:
        signal_label = 'weakening_long'
    elif dif_val > dea_val and hist_val > 0:
        signal_label = 'long'
    elif dif_val < dea_val and hist_val < 0 and hist_val > prev_hist:
        signal_label = 'weakening_short'
    elif dif_val < dea_val and hist_val < 0:
        signal_label = 'short'
    elif dif_val > dea_val and hist_val < 0:
        signal_label = 'golden_cross_pending'
    elif dif_val < dea_val and hist_val > 0:
        signal_label = 'death_cross_pending'
    else:
        signal_label = 'neutral'

    # Divergence detection
    divergence = _detect_macd_divergence(df, dif, dea)

    return {
        'macd_dif': round(dif_val, 4),
        'macd_dea': round(dea_val, 4),
        'macd_hist': round(hist_val, 4),
        'macd_signal': signal_label,
        'macd_divergence': divergence,
    }


def _detect_macd_divergence(df, dif, dea, lookback=30):
    """Detect MACD divergence (顶背离/底背离)"""
    if len(df) < lookback:
        return 'none'

    recent_close = df['close'].tail(lookback)
    recent_dif = dif.tail(lookback)

    price_high_idx = recent_close.idxmax()
    price_low_idx = recent_close.idxmin()
    dif_high_idx = recent_dif.idxmax()
    dif_low_idx = recent_dif.idxmin()

    # Bearish divergence: price makes higher high but DIF makes lower high
    if price_high_idx != dif_high_idx:
        price_max = recent_close.max()
        dif_at_price_max = dif.loc[price_high_idx]
        dif_max = recent_dif.max()
        price_at_dif_max = recent_close.loc[dif_high_idx]
        if price_max > price_at_dif_max * 1.02 and dif_max < dif_at_price_max * 0.9:
            return 'bearish'

    # Bullish divergence: price makes lower low but DIF makes higher low
    if price_low_idx != dif_low_idx:
        price_min = recent_close.min()
        dif_at_price_min = dif.loc[price_low_idx]
        dif_min = recent_dif.min()
        price_at_dif_min = recent_close.loc[dif_low_idx]
        if price_min < price_at_dif_min * 0.98 and dif_min > dif_at_price_min * 1.1:
            return 'bullish'

    return 'none'


# ============================================================
# RSI
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
# KDJ
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
    """Calculate Bollinger Bands with squeeze/expansion detection"""
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

    bandwidth = (upper_val - lower_val) / mid_val * 100 if mid_val > 0 else 0

    # Squeeze detection: bandwidth at 20-period minimum
    bandwidth_series = (upper - lower) / mid * 100
    if len(bandwidth_series) >= 20:
        recent_bw = bandwidth_series.tail(20)
        if bandwidth <= recent_bw.quantile(0.1):
            squeeze = 'squeeze'
        elif bandwidth >= recent_bw.quantile(0.9):
            squeeze = 'expansion'
        else:
            squeeze = 'normal'
    else:
        squeeze = 'normal'

    return {
        'boll_upper': round(upper_val, 2),
        'boll_mid': round(mid_val, 2),
        'boll_lower': round(lower_val, 2),
        'boll_pct_b': round(float(pct_b), 3),
        'boll_width': round(float(bandwidth), 2),
        'boll_squeeze': squeeze,
        'boll_position': position,
    }


# ============================================================
# ATR — Average True Range
# ============================================================

def _calc_atr(df, period=14):
    """ATR for volatility measurement"""
    if len(df) < period:
        return {'atr': 0, 'atr_pct': 0}

    high, low, close = df['high'], df['low'], df['close']
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = float(tr.rolling(window=period).mean().iloc[-1])
    price = float(close.iloc[-1])
    atr_pct = (atr / price) * 100 if price > 0 else 0

    return {'atr': round(atr, 2), 'atr_pct': round(float(atr_pct), 2)}


# ============================================================
# CCI — Commodity Channel Index
# ============================================================

def _calc_cci(df, period=14):
    """CCI — measures price deviation from statistical mean"""
    if len(df) < period:
        return {'cci': 0, 'cci_signal': 'neutral'}

    tp = (df['high'] + df['low'] + df['close']) / 3
    sma = tp.rolling(window=period).mean()
    mad = tp.rolling(window=period).apply(lambda x: np.mean(np.abs(x - np.mean(x))))

    cci_val = (tp.iloc[-1] - sma.iloc[-1]) / (0.015 * mad.iloc[-1]) if mad.iloc[-1] != 0 else 0

    if cci_val > 100:
        signal = 'overbought'
    elif cci_val < -100:
        signal = 'oversold'
    else:
        signal = 'neutral'

    return {'cci': round(float(cci_val), 2), 'cci_signal': signal}


# ============================================================
# Williams %R
# ============================================================

def _calc_williams_r(df, period=14):
    """Williams %R — similar to stochastic but inverted"""
    if len(df) < period:
        return {'wr': -50, 'wr_signal': 'neutral'}

    high_n = df['high'].rolling(window=period).max()
    low_n = df['low'].rolling(window=period).min()
    wr = (high_n - df['close']) / (high_n - low_n) * -100
    wr_val = float(wr.iloc[-1])

    if wr_val > -20:
        signal = 'overbought'
    elif wr_val < -80:
        signal = 'oversold'
    else:
        signal = 'neutral'

    return {'wr': round(wr_val, 2), 'wr_signal': signal}


# ============================================================
# OBV — On-Balance Volume
# ============================================================

def _calc_obv(df):
    """OBV with trend comparison"""
    if len(df) < 5 or 'volume' not in df.columns:
        return {'obv_signal': 'neutral'}

    close_diff = df['close'].diff()
    obv = pd.Series(index=df.index, dtype=float)
    obv.iloc[0] = float(df['volume'].iloc[0])

    for i in range(1, len(df)):
        if close_diff.iloc[i] > 0:
            obv.iloc[i] = obv.iloc[i-1] + float(df['volume'].iloc[i])
        elif close_diff.iloc[i] < 0:
            obv.iloc[i] = obv.iloc[i-1] - float(df['volume'].iloc[i])
        else:
            obv.iloc[i] = obv.iloc[i-1]

    obv_ma5 = obv.tail(5).mean()
    obv_ma20 = obv.tail(20).mean() if len(obv) >= 20 else obv_ma5
    obv_trend = 'rising' if obv_ma5 > obv_ma20 else 'falling'

    # OBV divergence with price
    price_trend = 'rising' if df['close'].iloc[-1] > df['close'].iloc[-5] else 'falling'
    if price_trend == 'rising' and obv_trend == 'falling':
        signal = 'bearish_divergence'
    elif price_trend == 'falling' and obv_trend == 'rising':
        signal = 'bullish_divergence'
    else:
        signal = 'neutral'

    return {'obv_signal': signal, 'obv_trend': obv_trend}


# ============================================================
# MFI — Money Flow Index
# ============================================================

def _calc_mfi(df, period=14):
    """MFI — volume-weighted RSI"""
    if len(df) < period or 'volume' not in df.columns:
        return {'mfi': 50, 'mfi_signal': 'neutral'}

    tp = (df['high'] + df['low'] + df['close']) / 3
    money_flow = tp * df['volume']

    positive_flow = pd.Series(0.0, index=df.index)
    negative_flow = pd.Series(0.0, index=df.index)

    for i in range(1, len(df)):
        if tp.iloc[i] > tp.iloc[i-1]:
            positive_flow.iloc[i] = money_flow.iloc[i]
        elif tp.iloc[i] < tp.iloc[i-1]:
            negative_flow.iloc[i] = money_flow.iloc[i]

    pos_sum = positive_flow.rolling(window=period).sum()
    neg_sum = negative_flow.rolling(window=period).sum()

    mf_ratio = pos_sum / neg_sum.replace(0, np.inf)
    mfi = 100 - (100 / (1 + mf_ratio))
    mfi_val = float(mfi.iloc[-1]) if not pd.isna(mfi.iloc[-1]) else 50

    if mfi_val > 80:
        signal = 'overbought'
    elif mfi_val < 20:
        signal = 'oversold'
    else:
        signal = 'neutral'

    return {'mfi': round(mfi_val, 2), 'mfi_signal': signal}


# ============================================================
# ADX — Average Directional Index
# ============================================================

def _calc_adx(df, period=14):
    """ADX + DI+/DI- for trend strength"""
    if len(df) < period * 2:
        return {'adx': 0, 'adx_di_plus': 0, 'adx_di_minus': 0, 'adx_signal': 'weak'}

    high, low, close = df['high'], df['low'], df['close']
    prev_close = close.shift(1)

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(0.0, index=df.index)
    minus_dm = pd.Series(0.0, index=df.index)

    for i in range(1, len(df)):
        if up_move.iloc[i] > down_move.iloc[i] and up_move.iloc[i] > 0:
            plus_dm.iloc[i] = up_move.iloc[i]
        if down_move.iloc[i] > up_move.iloc[i] and down_move.iloc[i] > 0:
            minus_dm.iloc[i] = down_move.iloc[i]

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr_smooth = tr.rolling(window=period).mean()
    plus_di = 100 * plus_dm.rolling(window=period).mean() / atr_smooth.replace(0, np.inf)
    minus_di = 100 * minus_dm.rolling(window=period).mean() / atr_smooth.replace(0, np.inf)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.inf)
    adx = dx.rolling(window=period).mean()

    adx_val = float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 0
    plus_val = float(plus_di.iloc[-1]) if not pd.isna(plus_di.iloc[-1]) else 0
    minus_val = float(minus_di.iloc[-1]) if not pd.isna(minus_di.iloc[-1]) else 0

    if adx_val > 40:
        strength = 'strong'
    elif adx_val > 25:
        strength = 'present'
    else:
        strength = 'weak'

    if plus_val > minus_val:
        direction = 'bullish'
    else:
        direction = 'bearish'

    return {
        'adx': round(adx_val, 2),
        'adx_di_plus': round(plus_val, 2),
        'adx_di_minus': round(minus_val, 2),
        'adx_signal': f'{strength}_{direction}',
    }


# ============================================================
# PSY — Psychological Line
# ============================================================

def _calc_psy(df, period=12):
    """PSY — ratio of rising days in period"""
    if len(df) < period:
        return {'psy': 50, 'psy_signal': 'neutral'}

    up_days = (df['close'].diff() > 0).rolling(window=period).sum()
    psy_val = float(up_days.iloc[-1] / period * 100)

    if psy_val > 75:
        signal = 'overbought'
    elif psy_val < 25:
        signal = 'oversold'
    else:
        signal = 'neutral'

    return {'psy': round(psy_val, 2), 'psy_signal': signal}


# ============================================================
# VR — Volume Ratio
# ============================================================

def _calc_vr(df, period=26):
    """VR — volume-based overbought/oversold"""
    if len(df) < period or 'volume' not in df.columns:
        return {'vr': 100, 'vr_signal': 'neutral'}

    close_diff = df['close'].diff()
    up_vol = df['volume'].where(close_diff > 0, 0).rolling(window=period).sum()
    down_vol = df['volume'].where(close_diff < 0, 0).rolling(window=period).sum()
    flat_vol = df['volume'].where(close_diff == 0, 0).rolling(window=period).sum()

    vr = (up_vol + 0.5 * flat_vol) / (down_vol + 0.5 * flat_vol).replace(0, np.inf) * 100
    vr_val = float(vr.iloc[-1]) if not pd.isna(vr.iloc[-1]) else 100

    if vr_val > 450:
        signal = 'extreme_overbought'
    elif vr_val > 160:
        signal = 'overbought'
    elif vr_val < 40:
        signal = 'oversold'
    elif vr_val < 70:
        signal = 'potential_floor'
    else:
        signal = 'neutral'

    return {'vr': round(vr_val, 2), 'vr_signal': signal}


# ============================================================
# DMA — Different of Moving Average
# ============================================================

def _calc_dma(df, short=10, long=50, m=10):
    """DMA — 平行线差指标"""
    if len(df) < long + m:
        return {'dma': 0, 'dma_ama': 0, 'dma_signal': 'neutral'}

    short_ma = df['close'].rolling(window=short).mean()
    long_ma = df['close'].rolling(window=long).mean()
    diff = short_ma - long_ma
    ama = diff.rolling(window=m).mean()

    dma_val = float(diff.iloc[-1])
    ama_val = float(ama.iloc[-1])

    prev_dma = float(diff.iloc[-2]) if len(diff) > 1 else dma_val
    prev_ama = float(ama.iloc[-2]) if len(ama) > 1 else ama_val

    if prev_dma < prev_ama and dma_val > ama_val:
        signal = 'golden_cross'
    elif prev_dma > prev_ama and dma_val < ama_val:
        signal = 'death_cross'
    else:
        signal = 'neutral'

    return {'dma': round(dma_val, 2), 'dma_ama': round(ama_val, 2), 'dma_signal': signal}


# ============================================================
# TRIX — Triple Exponential Average
# ============================================================

def _calc_trix(df, period=12, signal_period=9):
    """TRIX — triple-smoothed EMA oscillator"""
    if len(df) < period + signal_period + 3:
        return {'trix': 0, 'trix_signal': 'neutral'}

    ema1 = df['close'].ewm(span=period, adjust=False).mean()
    ema2 = ema1.ewm(span=period, adjust=False).mean()
    ema3 = ema2.ewm(span=period, adjust=False).mean()
    trix = ema3.pct_change() * 100
    trix_ma = trix.ewm(span=signal_period, adjust=False).mean()

    trix_val = float(trix.iloc[-1])
    trix_ma_val = float(trix_ma.iloc[-1])

    prev_trix = float(trix.iloc[-2]) if len(trix) > 1 else trix_val
    prev_trix_ma = float(trix_ma.iloc[-2]) if len(trix_ma) > 1 else trix_ma_val

    if prev_trix < prev_trix_ma and trix_val > trix_ma_val:
        signal = 'golden_cross'
    elif prev_trix > prev_trix_ma and trix_val < trix_ma_val:
        signal = 'death_cross'
    else:
        signal = 'neutral'

    return {'trix': round(trix_val, 4), 'trix_ma': round(trix_ma_val, 4), 'trix_signal': signal}


# ============================================================
# BBIBOLL — BBI + Bollinger
# ============================================================

def _calc_bbiboll(df, ma_periods=(3, 6, 12, 24), std_period=11, std_dev=2):
    """BBIBOLL — 多空指标"""
    if len(df) < max(ma_periods) + std_period:
        return {'bbiboll_upper': 0, 'bbiboll_mid': 0, 'bbiboll_lower': 0, 'bbiboll_signal': 'neutral'}

    bbi = sum(df['close'].rolling(window=p).mean() for p in ma_periods) / len(ma_periods)
    std = df['close'].rolling(window=std_period).std()

    upper = bbi + std_dev * std
    lower = bbi - std_dev * std

    bbi_val = float(bbi.iloc[-1])
    upper_val = float(upper.iloc[-1])
    lower_val = float(lower.iloc[-1])
    price = float(df['close'].iloc[-1])

    prev_price = float(df['close'].iloc[-2]) if len(df) > 1 else price
    prev_bbi = float(bbi.iloc[-2]) if len(bbi) > 1 else bbi_val

    if prev_price < prev_bbi and price > bbi_val:
        signal = 'bullish_cross'
    elif prev_price > prev_bbi and price < bbi_val:
        signal = 'bearish_cross'
    elif price > upper_val:
        signal = 'overbought'
    elif price < lower_val:
        signal = 'oversold'
    else:
        signal = 'neutral'

    return {
        'bbiboll_upper': round(upper_val, 2),
        'bbiboll_mid': round(bbi_val, 2),
        'bbiboll_lower': round(lower_val, 2),
        'bbiboll_signal': signal,
    }


# ============================================================
# Keltner Channel
# ============================================================

def _calc_keltner(df, ema_period=20, atr_mult=2):
    """Keltner Channel — EMA + ATR multiplier"""
    if len(df) < ema_period + 14:
        return {'keltner_upper': 0, 'keltner_mid': 0, 'keltner_lower': 0, 'keltner_signal': 'neutral'}

    ema = df['close'].ewm(span=ema_period, adjust=False).mean()
    atr_data = _compute_atr_series(df)
    atr = atr_data.iloc[-1] if len(atr_data) > 0 else 0

    upper = ema.iloc[-1] + atr_mult * atr
    mid = ema.iloc[-1]
    lower = ema.iloc[-1] - atr_mult * atr
    price = df['close'].iloc[-1]

    if price > upper:
        signal = 'above_upper'
    elif price < lower:
        signal = 'below_lower'
    else:
        signal = 'inside'

    return {
        'keltner_upper': round(float(upper), 2),
        'keltner_mid': round(float(mid), 2),
        'keltner_lower': round(float(lower), 2),
        'keltner_signal': signal,
    }


def _compute_atr_series(df, period=14):
    """Helper: compute ATR series"""
    high, low, close = df['high'], df['low'], df['close']
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


# ============================================================
# Ichimoku Cloud (一目均衡表) — simplified
# ============================================================

def _calc_ichimoku(df):
    """Ichimoku Cloud — Tenkan/Kijun/Senkou spans"""
    if len(df) < 52:
        return {'ichimoku_signal': 'neutral'}

    high, low, close = df['high'], df['low'], df['close']

    # Tenkan-sen (Conversion Line): (9-period high + 9-period low) / 2
    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2

    # Kijun-sen (Base Line): (26-period high + 26-period low) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2

    # Senkou Span A: (Tenkan + Kijun) / 2 displaced 26 periods forward
    senkou_a = ((tenkan + kijun) / 2).shift(26)

    # Senkou Span B: (52-period high + 52-period low) / 2 displaced 26 periods forward
    senkou_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)

    tenkan_val = float(tenkan.iloc[-1])
    kijun_val = float(kijun.iloc[-1])
    price = float(close.iloc[-1])
    cloud_top = float(senkou_a.iloc[-1]) if pd.notna(senkou_a.iloc[-1]) else 0
    cloud_bot = float(senkou_b.iloc[-1]) if pd.notna(senkou_b.iloc[-1]) else 0

    # Signal logic
    sig_parts = []
    if price > max(cloud_top, cloud_bot):
        sig_parts.append('above_cloud')
    elif price < min(cloud_top, cloud_bot):
        sig_parts.append('below_cloud')
    else:
        sig_parts.append('in_cloud')

    if tenkan_val > kijun_val:
        sig_parts.append('bullish')
    else:
        sig_parts.append('bearish')

    if cloud_top > cloud_bot:
        sig_parts.append('green_cloud')
    else:
        sig_parts.append('red_cloud')

    return {
        'ichimoku_tenkan': round(tenkan_val, 2),
        'ichimoku_kijun': round(kijun_val, 2),
        'ichimoku_cloud_top': round(cloud_top, 2),
        'ichimoku_cloud_bot': round(cloud_bot, 2),
        'ichimoku_signal': '_'.join(sig_parts),
    }


# ============================================================
# Support & Resistance
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

    pivot = (prev_high + prev_low + prev_close) / 3
    resistance = high
    support = low

    # Additional pivot levels
    r1 = 2 * pivot - prev_low
    r2 = pivot + (prev_high - prev_low)
    r3 = prev_high + 2 * (pivot - prev_low)
    s1 = 2 * pivot - prev_high
    s2 = pivot - (prev_high - prev_low)
    s3 = prev_low - 2 * (prev_high - pivot)

    dist_to_res = (resistance - close) / close * 100
    dist_to_sup = (close - support) / close * 100

    return {
        'resistance': round(resistance, 2),
        'support': round(support, 2),
        'pivot': round(pivot, 2),
        'r1': round(r1, 2), 'r2': round(r2, 2), 'r3': round(r3, 2),
        's1': round(s1, 2), 's2': round(s2, 2), 's3': round(s3, 2),
        'dist_to_res_pct': round(float(dist_to_res), 2),
        'dist_to_sup_pct': round(float(dist_to_sup), 2),
    }


# ============================================================
# Volume-Price Analysis (enhanced)
# ============================================================

def _calc_volume_price(df, period=20):
    """Volume-price relationship analysis with VWAP"""
    if len(df) < period or 'volume' not in df.columns:
        return {'vol_trend': 'neutral', 'vol_ratio': 1.0, 'vol_price_signal': 'neutral'}

    volume = df['volume']
    close = df['close']

    vol_ma5 = volume.tail(5).mean()
    vol_ma20 = volume.tail(period).mean()
    vol_ratio = vol_ma5 / vol_ma20 if vol_ma20 > 0 else 1.0

    price_change = close.iloc[-1] / close.iloc[-5] - 1 if len(close) >= 5 else 0

    if price_change > 0.02 and vol_ratio > 1.5:
        signal = 'strong_uptrend'
    elif price_change > 0.02 and vol_ratio < 0.8:
        signal = 'weak_uptrend'
    elif price_change < -0.02 and vol_ratio > 1.5:
        signal = 'strong_downtrend'
    elif price_change < -0.02 and vol_ratio < 0.8:
        signal = 'weak_downtrend'
    elif vol_ratio > 1.5:
        signal = 'high_volume_neutral'
    elif vol_ratio < 0.5:
        signal = 'extreme_low_volume'
    else:
        signal = 'neutral'

    # VWAP (Volume-Weighted Average Price) for last 20 days
    vwap_recent = (close.tail(period) * volume.tail(period)).sum() / volume.tail(period).sum() \
        if volume.tail(period).sum() > 0 else 0

    return {
        'vol_trend': 'increase' if vol_ratio > 1.2 else ('decrease' if vol_ratio < 0.8 else 'stable'),
        'vol_ratio': round(float(vol_ratio), 2),
        'vol_price_signal': signal,
        'vwap_20': round(float(vwap_recent), 2),
    }


# ============================================================
# Composite Trend Detail (main API — backward compatible)
# ============================================================

def get_trend_detail(df):
    """Return detailed trend information with ALL indicators (25+).
    This is the main API entry point — returns a flat dict.
    """
    if df.empty:
        return {}

    close = df['close'].iloc[-1]
    prev = df['close'].iloc[-2] if len(df) > 1 else close
    change = close - prev
    pct = (change / prev) * 100 if prev != 0 else 0

    # Core
    result = {
        'close': float(close),
        'change': round(float(change), 2),
        'change_pct': round(float(pct), 2),
        'ma5': float(df.get('MA5', pd.Series([0]*len(df))).iloc[-1]),
        'ma10': float(df.get('MA10', pd.Series([0]*len(df))).iloc[-1]),
        'ma20': float(df.get('MA20', pd.Series([0]*len(df))).iloc[-1]),
        'ma60': float(df.get('MA60', pd.Series([0]*len(df))).iloc[-1]),
        'trend': get_trend(df),
    }

    # Existing indicators
    result.update(_calc_macd(df))
    result.update(_calc_rsi(df))
    result.update(_calc_kdj(df))
    result.update(_calc_boll(df))
    result.update(_calc_support_resistance(df))
    result.update(_calc_volume_price(df))

    # NEW indicators
    result.update(_calc_ma_deviation(df))
    result.update(_calc_atr(df))
    result.update(_calc_cci(df))
    result.update(_calc_williams_r(df))
    result.update(_calc_obv(df))
    result.update(_calc_mfi(df))
    result.update(_calc_adx(df))
    result.update(_calc_psy(df))
    result.update(_calc_vr(df))
    result.update(_calc_dma(df))
    result.update(_calc_trix(df))
    result.update(_calc_bbiboll(df))
    result.update(_calc_keltner(df))
    result.update(_calc_ichimoku(df))

    return result


# ============================================================
# Candlestick Pattern Recognition
# ============================================================

def detect_candlestick_patterns(df):
    """Detect common candlestick patterns.
    Returns a dict with pattern names as keys and boolean values.
    """
    if len(df) < 3:
        return {'doji': False, 'hammer': False, 'shooting_star': False,
                'engulfing_bullish': False, 'engulfing_bearish': False,
                'morning_star': False, 'evening_star': False}

    patterns = {}

    o = df['open'].values
    h = df['high'].values
    l = df['low'].values
    c = df['close'].values

    i = -1  # latest candle
    body = abs(c[i] - o[i])
    upper_shadow = h[i] - max(c[i], o[i])
    lower_shadow = min(c[i], o[i]) - l[i]
    total_range = h[i] - l[i]

    # Doji: tiny body
    patterns['doji'] = total_range > 0 and body / total_range < 0.1

    # Hammer: long lower shadow, small body, little upper shadow
    patterns['hammer'] = (
        lower_shadow > 2 * body and
        upper_shadow < 0.3 * body and
        total_range > 0 and
        c[i] > o[i]  # bullish close
    )

    # Shooting Star: long upper shadow, small body, little lower shadow
    patterns['shooting_star'] = (
        upper_shadow > 2 * body and
        lower_shadow < 0.3 * body and
        total_range > 0 and
        c[i] < o[i]  # bearish close
    )

    # Inverted Hammer
    patterns['inverted_hammer'] = (
        upper_shadow > 2 * body and
        lower_shadow < 0.3 * body and
        total_range > 0 and
        c[i] > o[i]
    )

    # Hanging Man
    patterns['hanging_man'] = (
        lower_shadow > 2 * body and
        upper_shadow < 0.3 * body and
        total_range > 0 and
        c[i] < o[i]
    )

    # Marubozu: full body, no shadows
    patterns['marubozu_bullish'] = (
        c[i] > o[i] and
        upper_shadow < 0.05 * body and
        lower_shadow < 0.05 * body
    )
    patterns['marubozu_bearish'] = (
        c[i] < o[i] and
        upper_shadow < 0.05 * body and
        lower_shadow < 0.05 * body
    )

    # Engulfing patterns (need previous candle)
    if len(df) >= 2:
        prev_body = abs(c[-2] - o[-2])
        prev_bullish = c[-2] > o[-2]

        patterns['engulfing_bullish'] = (
            not prev_bullish and c[i] > o[i] and
            o[i] < c[-2] and c[i] > o[-2] and
            body > prev_body
        )
        patterns['engulfing_bearish'] = (
            prev_bullish and c[i] < o[i] and
            o[i] > c[-2] and c[i] < o[-2] and
            body > prev_body
        )

    # Three-candle patterns
    if len(df) >= 3:
        patterns['morning_star'] = (
            c[-3] < o[-3] and  # bearish day 1
            abs(c[-2] - o[-2]) < body * 0.3 and  # small body day 2
            c[i] > o[i] and c[i] > (o[-3] + c[-3]) / 2  # bullish day 3
        )
        patterns['evening_star'] = (
            c[-3] > o[-3] and  # bullish day 1
            abs(c[-2] - o[-2]) < body * 0.3 and  # small body day 2
            c[i] < o[i] and c[i] < (o[-3] + c[-3]) / 2  # bearish day 3
        )

    # Three White Soldiers / Three Black Crows
    if len(df) >= 3:
        day1, day2, day3 = -3, -2, -1
        patterns['three_white_soldiers'] = (
            c[day1] > o[day1] and c[day2] > o[day2] and c[day3] > o[day3] and
            c[day2] > c[day1] and c[day3] > c[day2] and
            o[day2] > o[day1] and o[day3] > o[day2]
        )
        patterns['three_black_crows'] = (
            c[day1] < o[day1] and c[day2] < o[day2] and c[day3] < o[day3] and
            c[day2] < c[day1] and c[day3] < c[day2] and
            o[day2] < o[day1] and o[day3] < o[day2]
        )

    return patterns


# ============================================================
# Price Anomaly Detection (Z-Score)
# ============================================================

def detect_price_anomaly(df, lookback=20, z_threshold=2.0):
    """Detect price anomalies using rolling Z-score on returns."""
    if len(df) < lookback:
        return {'anomaly': False, 'z_score': 0, 'direction': 'none'}

    returns = df['close'].pct_change().dropna()
    recent = returns.tail(lookback)
    mean_ret = recent.mean()
    std_ret = recent.std()

    if std_ret == 0:
        return {'anomaly': False, 'z_score': 0, 'direction': 'none'}

    latest_ret = returns.iloc[-1]
    z = (latest_ret - mean_ret) / std_ret

    if z > z_threshold:
        direction = 'up'
    elif z < -z_threshold:
        direction = 'down'
    else:
        direction = 'none'

    return {
        'anomaly': abs(z) > z_threshold,
        'anomaly_z_score': round(float(z), 2),
        'anomaly_direction': direction,
    }


# ============================================================
# Indicator Summary (text report helper)
# ============================================================

def get_indicator_summary(indicators):
    """Generate a human-readable summary of all indicators."""
    lines = []
    lines.append("─" * 50)
    lines.append("  Technical Indicator Summary")
    lines.append("─" * 50)

    # Trend
    lines.append(f"  Price: {indicators.get('close', 0):.2f}  "
                 f"Change: {indicators.get('change_pct', 0):+.2f}%")
    lines.append(f"  MA  5/10/20/60: {indicators.get('ma5',0):.2f} / "
                 f"{indicators.get('ma10',0):.2f} / {indicators.get('ma20',0):.2f} / "
                 f"{indicators.get('ma60',0):.2f}")
    lines.append(f"  Trend: {indicators.get('trend', 'unknown')}")
    lines.append(f"  BIAS: 5d={indicators.get('bias_ma5',0):.1f}% "
                 f"10d={indicators.get('bias_ma10',0):.1f}% "
                 f"20d={indicators.get('bias_ma20',0):.1f}%")

    lines.append("  ── Oscillators ──")
    lines.append(f"  RSI(14): {indicators.get('rsi',0):.1f} [{indicators.get('rsi_signal','')}]")
    lines.append(f"  KDJ: K={indicators.get('k',0):.1f} D={indicators.get('d',0):.1f} "
                 f"J={indicators.get('j',0):.1f} [{indicators.get('kdj_signal','')}]")
    lines.append(f"  MACD: DIF={indicators.get('macd_dif',0):.4f} "
                 f"DEA={indicators.get('macd_dea',0):.4f} "
                 f"HIST={indicators.get('macd_hist',0):.4f}")
    lines.append(f"   Divergence: {indicators.get('macd_divergence', 'none')}")
    lines.append(f"  CCI(14): {indicators.get('cci',0):.1f} [{indicators.get('cci_signal','')}]")
    lines.append(f"  WR(14): {indicators.get('wr',0):.1f} [{indicators.get('wr_signal','')}]")
    lines.append(f"  MFI(14): {indicators.get('mfi',0):.1f} [{indicators.get('mfi_signal','')}]")
    lines.append(f"  PSY(12): {indicators.get('psy',0):.1f} [{indicators.get('psy_signal','')}]")
    lines.append(f"  TRIX: {indicators.get('trix',0):.4f} [{indicators.get('trix_signal','')}]")
    lines.append(f"  DMA: {indicators.get('dma',0):.4f} [{indicators.get('dma_signal','')}]")
    lines.append(f"  VR: {indicators.get('vr',0):.1f} [{indicators.get('vr_signal','')}]")

    lines.append("  ── Trend Strength ──")
    lines.append(f"  ADX(14): {indicators.get('adx',0):.1f} "
                 f"DI+={indicators.get('adx_di_plus',0):.1f} "
                 f"DI-={indicators.get('adx_di_minus',0):.1f} "
                 f"[{indicators.get('adx_signal','')}]")
    lines.append(f"  ATR(14): {indicators.get('atr',0):.2f} ({indicators.get('atr_pct',0):.1f}%)")

    lines.append("  ── Channels ──")
    lines.append(f"  Bollinger: U={indicators.get('boll_upper',0):.2f} "
                 f"M={indicators.get('boll_mid',0):.2f} "
                 f"L={indicators.get('boll_lower',0):.2f}")
    lines.append(f"    %B={indicators.get('boll_pct_b',0):.3f} "
                 f"Width={indicators.get('boll_width',0):.1f}% "
                 f"[{indicators.get('boll_squeeze','')}] "
                 f"{indicators.get('boll_position','')}")
    lines.append(f"  BBIBOLL: U={indicators.get('bbiboll_upper',0):.2f} "
                 f"M={indicators.get('bbiboll_mid',0):.2f} "
                 f"L={indicators.get('bbiboll_lower',0):.2f}")
    lines.append(f"  Keltner: U={indicators.get('keltner_upper',0):.2f} "
                 f"M={indicators.get('keltner_mid',0):.2f} "
                 f"L={indicators.get('keltner_lower',0):.2f}")
    lines.append(f"  Ichimoku: Tenkan={indicators.get('ichimoku_tenkan',0):.2f} "
                 f"Kijun={indicators.get('ichimoku_kijun',0):.2f}")
    lines.append(f"    Cloud: {indicators.get('ichimoku_cloud_top',0):.2f} / "
                 f"{indicators.get('ichimoku_cloud_bot',0):.2f}")

    lines.append("  ── Volume & Support ──")
    lines.append(f"  Volume: ratio={indicators.get('vol_ratio',0):.1f}x "
                 f"[{indicators.get('vol_price_signal','')}]")
    lines.append(f"  VWAP(20): {indicators.get('vwap_20',0):.2f}")
    lines.append(f"  OBV: {indicators.get('obv_signal','')} ({indicators.get('obv_trend','')})")
    lines.append(f"  Support: {indicators.get('support',0):.2f} "
                 f"({indicators.get('dist_to_sup_pct',0):.1f}% away)")
    lines.append(f"  Resistance: {indicators.get('resistance',0):.2f} "
                 f"({indicators.get('dist_to_res_pct',0):.1f}% away)")
    lines.append(f"  Pivot: {indicators.get('pivot',0):.2f} "
                 f"R1={indicators.get('r1',0):.2f} S1={indicators.get('s1',0):.2f}")
    lines.append("─" * 50)

    return '\\n'.join(lines)
