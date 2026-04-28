#!/usr/bin/env python3
# TradeMind Plain-Talk Analysis - retail-friendly conclusions
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def plain_talk(symbol):
    from data.price import get_latest_price, get_price_data
    from analysis.technical import get_trend_detail
    from analysis.scoring import get_score, get_signal
    
    info = get_latest_price(symbol)
    if not info or 'error' in info:
        return 'Unable to fetch data for ' + str(symbol)
    
    name = info.get('name', symbol)
    price = info.get('price', 0)
    change = info.get('change_pct', 0)
    
    lines = []
    lines.append('=' * 50)
    lines.append('  ' + name + ' (' + symbol + ')  ' + format(price, '.2f'))
    lines.append('=' * 50)
    
    # Price action
    if change > 3:
        lines.append('')
        lines.append('Today: ' + format(change, '+.2f') + '% Strong rally, may continue')
    elif change > 0:
        lines.append('')
        lines.append('Today: ' + format(change, '+.2f') + '% Modest gain')
    elif change > -3:
        lines.append('')
        lines.append('Today: ' + format(change, '+.2f') + '% Slight pullback, normal')
    else:
        lines.append('')
        lines.append('Today: ' + format(change, '+.2f') + '% Sharp drop - exercise caution')
    
    # Technical
    try:
        trend = get_trend_detail(symbol)
        if trend:
            t = trend.get('trend', 'sideways')
            s = trend.get('strength', 'weak')
            if t == 'up' and s == 'strong':
                lines.append('Trend: Strong uptrend - favors holding/buying')
            elif t == 'up':
                lines.append('Trend: Uptrend - OK to hold')
            elif t == 'down' and s == 'strong':
                lines.append('Trend: Strong downtrend - consider reducing')
            elif t == 'down':
                lines.append('Trend: Downtrend - wait for reversal signal')
            else:
                lines.append('Trend: Sideways - wait for direction')
    except:
        pass
    
    # Scoring
    try:
        score = get_score(symbol)
        signal = get_signal(symbol)
        if score:
            if score >= 75:
                lines.append('Score: ' + str(score) + '/100 Excellent - consider buying')
            elif score >= 60:
                lines.append('Score: ' + str(score) + '/100 Good - hold or light buy')
            elif score >= 40:
                lines.append('Score: ' + str(score) + '/100 Fair - hold, no action')
            else:
                lines.append('Score: ' + str(score) + '/100 Weak - reduce or avoid')
    except:
        pass
    
    # Bottom line
    lines.append('')
    lines.append('-' * 50)
    try:
        s = get_signal(symbol)
        if s == 'buy':
            lines.append('BOTTOM LINE: Buy signal - fundamentals + technicals aligned')
        elif s == 'hold':
            lines.append('BOTTOM LINE: Hold - no clear sell signal, wait')
        elif s == 'sell':
            lines.append('BOTTOM LINE: Sell signal - consider reducing position')
        else:
            lines.append('BOTTOM LINE: Insufficient data - check back tomorrow')
    except:
        lines.append('BOTTOM LINE: Watch - monitor for signals')
    lines.append('-' * 50)
    return chr(10).join(lines)

if __name__ == '__main__':
    sym = sys.argv[1] if len(sys.argv) > 1 else '600519'
    print(plain_talk(sym))