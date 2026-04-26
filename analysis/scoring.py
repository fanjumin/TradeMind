def get_score(trend, fund_flow, basic_score, indicators=None):
    """
    Composite score 0-100

    Components:
      Technical trend (30 pts) - MA alignment + RSI + KDJ + Bollinger
      Fund flow (20 pts) - Volume/price relationship
      Fundamentals (50 pts) - basic_score * 0.5
    """
    score = 0

    # === Technical trend (30 pts) ===
    ts = {
        'strong_uptrend': 30,
        'uptrend': 24,
        'neutral': 15,
        'downtrend': 8,
    }
    score += ts.get(trend, 15)

    # RSI bonus/penalty (already factored in trend, but add fine-tuning)
    if indicators:
        rsi = indicators.get('rsi', 50)
        if 40 <= rsi <= 60:
            score += 0  # neutral, no adjustment
        elif 30 <= rsi < 40:
            score += 2  # approaching oversold, potential bounce
        elif rsi < 30:
            score += 3  # oversold, potential bounce (counter-trend)
        elif 60 < rsi <= 70:
            score += 1  # still room to run
        elif rsi > 80:
            score -= 2  # overbought risk

        # KDJ bonus
        kdj_signal = indicators.get('kdj_signal', 'neutral')
        if kdj_signal == 'bullish':
            score += 2
        elif kdj_signal == 'bearish':
            score -= 2
        elif kdj_signal == 'oversold':
            score += 2

        # Bollinger Bands bonus
        boll_pos = indicators.get('boll_position', 'neutral')
        if boll_pos == 'near_lower':
            score += 2
        elif boll_pos == 'near_upper':
            score -= 1

    # === Fund flow (20 pts) ===
    if fund_flow > 1e8:
        score += 20
    elif fund_flow > 0:
        score += 15
    elif fund_flow > -1e8:
        score += 10
    else:
        score += 5

    # === Fundamentals (50 pts) ===
    score += basic_score * 0.5

    return max(0, min(int(score), 100))


def get_signal(score):
    if score >= 70: return 'strong_buy'
    elif score >= 55: return 'buy'
    elif score >= 40: return 'hold'
    elif score >= 25: return 'reduce'
    else: return 'avoid'


def get_signal_cn(s):
    return {
        'strong_buy': '强烈买入',
        'buy': '买入',
        'hold': '持有',
        'reduce': '减仓',
        'avoid': '回避',
    }.get(s, s)
