def get_score(trend, fund_flow, basic_score):
    """Composite score 0-100"""
    score = 0
    ts = {
        'strong_uptrend': 40,
        'uptrend': 30,
        'neutral': 15,
        'downtrend': 5,
    }
    score += ts.get(trend, 15)
    
    if fund_flow > 0: score += 30
    elif fund_flow > -1e8: score += 15
    else: score += 5
    
    score += basic_score * 0.3
    
    return min(int(score), 100)


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
