"""
AI-based price prediction using simple ML models.
Uses historical patterns, technical indicators, and statistical methods.
No external ML dependencies - pure numpy/pandas implementation.
"""
import numpy as np
import pandas as pd


def predict_price(df, horizon=5, method='ensemble'):
    """
    Predict future price using multiple methods and ensemble.

    Parameters:
        df: DataFrame with OHLCV data
        horizon: days to predict ahead
        method: 'ensemble', 'ma_trend', 'regression', 'momentum'

    Returns:
        dict with predictions and confidence
    """
    if df.empty or len(df) < 20:
        return {'error': 'Insufficient data'}

    results = {
        'current_price': df['close'].iloc[-1],
        'horizon': horizon,
        'predictions': {},
        'consensus': 0,
        'confidence': 0,
        'target_price': 0,
        'upside': 0,
    }

    # Method 1: MA Trend Extrapolation
    ma_trend_pred = _predict_ma_trend(df, horizon)
    results['predictions']['ma_trend'] = ma_trend_pred

    # Method 2: Linear Regression
    lr_pred = _predict_regression(df, horizon)
    results['predictions']['linear_regression'] = lr_pred

    # Method 3: Momentum/Mean Reversion
    mom_pred = _predict_momentum(df, horizon)
    results['predictions']['momentum'] = mom_pred

    # Method 4: Bollinger Band projection
    boll_pred = _predict_bollinger(df, horizon)
    results['predictions']['bollinger'] = boll_pred

    # Ensemble: weighted average
    weights = {
        'ma_trend': 0.3,
        'linear_regression': 0.25,
        'momentum': 0.25,
        'bollinger': 0.2,
    }

    if method == 'ensemble':
        total_weight = 0
        weighted_sum = 0
        for name, weight in weights.items():
            pred = results['predictions'].get(name, {})
            if pred and pred.get('price', 0) > 0:
                weighted_sum += pred['price'] * weight
                total_weight += weight

        if total_weight > 0:
            results['consensus'] = round(weighted_sum / total_weight, 2)
            results['confidence'] = round(min(0.8, total_weight), 2)
    else:
        pred = results['predictions'].get(method, {})
        results['consensus'] = pred.get('price', 0)
        results['confidence'] = pred.get('confidence', 0)

    # Calculate upside
    current = results['current_price']
    if current > 0 and results['consensus'] > 0:
        results['target_price'] = results['consensus']
        results['upside'] = round((results['consensus'] - current) / current * 100, 2)

    return results


def _predict_ma_trend(df, horizon):
    """Predict based on MA trend extrapolation"""
    close = df['close']
    ma5 = close.rolling(5).mean().iloc[-1]
    ma10 = close.rolling(10).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]

    # Calculate daily trend rate
    recent_5 = close.tail(5)
    daily_change = recent_5.pct_change().mean()

    # Project forward
    current = close.iloc[-1]
    projected = current * (1 + daily_change) ** horizon

    # Adjust by MA alignment
    if ma5 > ma10 > ma20:
        projected *= 1.01  # Bullish boost
    elif ma5 < ma10 < ma20:
        projected *= 0.99  # Bearish drag

    return {
        'price': round(projected, 2),
        'confidence': 0.5,
        'direction': 'up' if projected > current else 'down',
    }


def _predict_regression(df, horizon):
    """Simple linear regression on recent prices"""
    n = min(30, len(df))
    recent = df['close'].tail(n).values
    x = np.arange(n)

    # Linear regression: y = ax + b
    x_mean = np.mean(x)
    y_mean = np.mean(recent)
    slope = np.sum((x - x_mean) * (recent - y_mean)) / np.sum((x - x_mean) ** 2)
    intercept = y_mean - slope * x_mean

    # Project
    projected = slope * (n + horizon - 1) + intercept

    # Confidence based on R-squared
    y_pred = slope * x + intercept
    ss_res = np.sum((recent - y_pred) ** 2)
    ss_tot = np.sum((recent - y_mean) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    current = df['close'].iloc[-1]
    return {
        'price': round(max(projected, current * 0.8), 2),  # Floor at -20%
        'confidence': round(abs(r_squared), 2),
        'direction': 'up' if slope > 0 else 'down',
        'slope': round(slope, 4),
    }


def _predict_momentum(df, horizon):
    """Momentum + mean reversion prediction"""
    close = df['close']
    current = close.iloc[-1]

    # RSI-based mean reversion
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean().iloc[-1]
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean().iloc[-1]
    rsi = 100 - (100 / (1 + gain / loss)) if loss > 0 else 100

    # Momentum from recent returns
    ret_5 = close.iloc[-1] / close.iloc[-5] - 1 if len(close) >= 5 else 0
    ret_10 = close.iloc[-1] / close.iloc[-10] - 1 if len(close) >= 10 else 0

    # Mean reversion: if RSI is extreme, expect reversion
    if rsi > 70:
        reversion = -0.02 * ((rsi - 70) / 30)  # Pull back from overbought
    elif rsi < 30:
        reversion = 0.02 * ((30 - rsi) / 30)  # Bounce from oversold
    else:
        reversion = 0

    # Project: momentum + mean reversion
    projected = current * (1 + ret_5 * horizon / 5 + reversion)

    return {
        'price': round(projected, 2),
        'confidence': 0.4,
        'direction': 'up' if projected > current else 'down',
        'rsi': round(rsi, 1),
    }


def _predict_bollinger(df, horizon):
    """Bollinger Band based prediction"""
    close = df['close']
    current = close.iloc[-1]

    ma20 = close.rolling(20).mean().iloc[-1]
    std20 = close.rolling(20).std().iloc[-1]

    upper = ma20 + 2 * std20
    lower = ma20 - 2 * std20

    # Price tends to revert to mean
    if current > upper:
        projected = ma20  # Revert to mean
    elif current < lower:
        projected = ma20  # Revert to mean
    else:
        # Continue trending within bands
        mid = (upper + lower) / 2
        projected = mid + (current - mid) * 0.9  # Slight mean reversion

    # Confidence based on band width (narrower = more reliable)
    bandwidth = (upper - lower) / ma20
    confidence = max(0.3, 1 - bandwidth)

    return {
        'price': round(projected, 2),
        'confidence': round(confidence, 2),
        'direction': 'up' if projected > current else 'down',
        'upper': round(upper, 2),
        'lower': round(lower, 2),
    }


def format_prediction_report(result):
    """Format prediction results as text"""
    if 'error' in result:
        return f"Prediction Error: {result['error']}"

    lines = []
    lines.append("=" * 60)
    lines.append("  TradeMind - Price Prediction")
    lines.append(f"  Current Price:  {result['current_price']}")
    lines.append(f"  Horizon:        {result['horizon']} days")
    lines.append("=" * 60)
    lines.append("")
    lines.append("--- Individual Methods ---")

    for name, pred in result['predictions'].items():
        if pred and pred.get('price', 0) > 0:
            direction = pred.get('direction', '?')
            arrow = '+' if direction == 'up' else '-'
            pct = (pred['price'] - result['current_price']) / result['current_price'] * 100
            lines.append(f"  {name:<20s} {pred['price']:.2f} ({arrow}{abs(pct):.1f}%, conf={pred.get('confidence', 0):.2f})")

    lines.append("")
    lines.append("--- Consensus ---")
    target = result.get('target_price', 0)
    upside = result.get('upside', 0)
    direction = "UP" if upside > 0 else "DOWN"
    lines.append(f"  Target Price:  {target:.2f}")
    lines.append(f"  Upside:        {upside:+.2f}%")
    lines.append(f"  Direction:     {direction}")
    lines.append(f"  Confidence:    {result.get('confidence', 0):.2f}")

    lines.append("")
    lines.append("=" * 60)
    lines.append("  Note: Predictions are statistical estimates, not guarantees.")
    lines.append("=" * 60)

    return '\n'.join(lines)
