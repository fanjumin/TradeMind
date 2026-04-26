import requests
import json


def _eastmoney_secid(symbol):
    """Convert stock code to EastMoney secid (market.code)"""
    clean = symbol.replace('.SZ', '').replace('.SH', '').replace('.BJ', '')
    if clean.startswith('6'):
        return '1.' + clean  # Shanghai
    elif clean.startswith(('0', '3')):
        return '0.' + clean  # Shenzhen
    elif clean.startswith(('8', '4')):
        return '0.' + clean  # Beijing (use 0 for now)
    else:
        return '0.' + clean


def get_fund_flow(symbol, days=5):
    """
    Get real capital flow data from EastMoney.
    Returns: (main_force_net_5d, detail_dict)

    detail_dict contains:
      - main_force_today: 主力净流入 (today)
      - super_large: 超大单净流入 (today)
      - large: 大单净流入 (today)
      - medium: 中单净流入 (today)
      - small: 小单净流入 (today)
      - main_force_pct: 主力净流入占比 (today)
      - main_force_5d_sum: 5日主力净流入合计
      - volume, amount: from Tencent
    """
    secid = _eastmoney_secid(symbol)

    url = "https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "lmt": str(days),
        "fields1": "f1,f2,f3,f4",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "secid": secid,
        "ut": "b2884a393a59ad64002292a3e90d46a5",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }

    result = {
        'main_force_today': 0,
        'super_large': 0,
        'large': 0,
        'medium': 0,
        'small': 0,
        'main_force_pct': 0,
        'main_force_5d_sum': 0,
        'volume': 0,
        'amount': 0,
    }

    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        data = json.loads(r.text)

        if data.get('data') and data['data'].get('klines'):
            klines = data['data']['klines']

            # Parse each day
            daily_flows = []
            for line in klines:
                parts = line.split(',')
                if len(parts) >= 6:
                    daily_flows.append({
                        'date': parts[0],
                        'main_force': float(parts[1]),
                        'small': float(parts[2]),
                        'medium': float(parts[3]),
                        'large': float(parts[4]),
                        'super_large': float(parts[5]),
                        'main_force_pct': float(parts[6]) if len(parts) > 6 else 0,
                        'close': float(parts[11]) if len(parts) > 11 else 0,
                        'change_pct': float(parts[12]) if len(parts) > 12 else 0,
                    })

            if daily_flows:
                today = daily_flows[0]
                result['main_force_today'] = today['main_force']
                result['super_large'] = today['super_large']
                result['large'] = today['large']
                result['medium'] = today['medium']
                result['small'] = today['small']
                result['main_force_pct'] = today['main_force_pct']

                # 5-day sum
                result['main_force_5d_sum'] = sum(d['main_force'] for d in daily_flows)

                # Store daily data
                result['daily_flows'] = daily_flows

    except Exception:
        pass

    # Also get volume/amount from Tencent
    try:
        clean = symbol.replace('.SZ', '').replace('.SH', '').replace('.BJ', '')
        if clean.startswith('6'):
            tencent_sym = 'sh' + clean
        elif clean.startswith(('0', '3')):
            tencent_sym = 'sz' + clean
        else:
            tencent_sym = 'bj' + clean

        url2 = "http://qt.gtimg.cn/q=" + tencent_sym
        r2 = requests.get(url2, timeout=5)
        text = r2.text.strip().strip(';')
        if '~' in text:
            parts = text.split('~')
            if len(parts) > 37:
                result['volume'] = float(parts[6]) if parts[6] else 0
                result['amount'] = float(parts[37]) if len(parts) > 37 and parts[37] else 0
    except Exception:
        pass

    # Return value for backward compatibility: flow score + detail
    flow_score = result['main_force_5d_sum']
    return flow_score, result


def get_fund_flow_detail(symbol):
    """Get detailed flow info (convenience function)"""
    score, detail = get_fund_flow(symbol)
    return detail


def get_fund_flow_signal(flow_score, main_force_today, main_force_pct):
    """
    Generate fund flow signal based on real capital flow data.
    Returns: (signal_cn, signal_en, strength)
    """
    if main_force_today > 5e8 and main_force_pct > 15:
        return '主力大幅流入', 'strong_inflow', 5
    elif main_force_today > 1e8 and main_force_pct > 5:
        return '主力净流入', 'inflow', 4
    elif main_force_today > 0:
        return '小幅净流入', 'weak_inflow', 3
    elif main_force_today > -1e8:
        return '小幅净流出', 'weak_outflow', 2
    elif main_force_today > -5e8:
        return '主力净流出', 'outflow', 1
    else:
        return '主力大幅流出', 'strong_outflow', 0
