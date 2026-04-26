"""
Valuation models: DCF (Discounted Cash Flow) and PEG ratio.
Multi-quarter financial history comparison.
"""
import baostock as bs
import requests
import os
import sys


def _bs_symbol(symbol):
    clean = symbol.replace('.SZ', '').replace('.SH', '').replace('.BJ', '')
    if clean.startswith('6'):
        return 'sh.' + clean
    elif clean.startswith(('0', '3')):
        return 'sz.' + clean
    elif clean.startswith(('8', '4')):
        return 'bj.' + clean
    else:
        return 'sz.' + clean


def _tencent_symbol(symbol):
    clean = symbol.replace('.SZ', '').replace('.SH', '').replace('.BJ', '')
    if clean.startswith('6'):
        return 'sh' + clean
    elif clean.startswith(('0', '3')):
        return 'sz' + clean
    else:
        return 'bj' + clean


def get_multi_quarter_history(symbol, years=4):
    """
    Get historical profit & growth data for multiple years.
    Returns list of dicts with quarterly data.
    """
    bs_sym = _bs_symbol(symbol)
    history = []
    devnull = open(os.devnull, 'w')
    old_out, old_err = sys.stdout, sys.stderr

    try:
        sys.stdout = devnull
        sys.stderr = devnull
        lg = bs.login()
        if lg.error_code != '0':
            return history

        import datetime
        current_year = datetime.datetime.now().year

        for year in range(current_year, current_year - years, -1):
            entry = {'year': year, 'quarters': {}}

            for q in [4, 3, 2, 1]:
                rs = bs.query_profit_data(code=bs_sym, year=year, quarter=q)
                if rs.error_code == '0' and rs.next():
                    row = rs.get_row_data()
                    cols = dict(zip(rs.fields, row))
                    entry['quarters'][f'Q{q}'] = {
                        'statDate': cols.get('statDate', ''),
                        'roe': float(cols.get('roeAvg', 0) or 0),
                        'npm': float(cols.get('npMargin', 0) or 0),
                        'eps': float(cols.get('epsTTM', 0) or 0),
                        'net_profit': float(cols.get('netProfit', 0) or 0),
                        'revenue': float(cols.get('MBRevenue', 0) or 0),
                    }

            # Growth data
            rs2 = bs.query_growth_data(code=bs_sym, year=year, quarter=4)
            if rs2.error_code == '0' and rs2.next():
                row2 = rs2.get_row_data()
                cols2 = dict(zip(rs2.fields, row2))
                entry['growth'] = {
                    'yoy_equity': float(cols2.get('YOYEquity', 0) or 0),
                    'yoy_net_income': float(cols2.get('YOYNI', 0) or 0),
                    'yoy_eps': float(cols2.get('YOYEPSBasic', 0) or 0),
                }

            history.append(entry)

        bs.logout()
    except Exception:
        pass
    finally:
        sys.stdout = old_out
        sys.stderr = old_err
        try:
            bs.logout()
        except:
            pass
        devnull.close()

    return history


def calc_peg(pe, growth_rate):
    """
    PEG Ratio = PE / (Growth Rate * 100)
    < 1: undervalued
    1-2: fair value
    > 2: overvalued
    """
    if growth_rate <= 0 or pe <= 0:
        return None
    peg = pe / (growth_rate * 100)
    return round(peg, 2)


def calc_dcf(free_cash_flow, growth_rate, discount_rate, terminal_growth, shares_outstanding, current_price):
    """
    Simplified DCF (2-stage):
    - Stage 1: High growth for 5 years
    - Stage 2: Terminal value with stable growth
    Returns: (intrinsic_value, upside_percent, recommendation)
    """
    if free_cash_flow <= 0 or discount_rate <= terminal_growth:
        return None, None, "insufficient_data"

    # Stage 1: Project FCF for 5 years
    pv_fcf = 0
    for t in range(1, 6):
        fcf_t = free_cash_flow * (1 + growth_rate) ** t
        pv = fcf_t / (1 + discount_rate) ** t
        pv_fcf += pv

    # Stage 2: Terminal value
    fcf_terminal = free_cash_flow * (1 + growth_rate) ** 5 * (1 + terminal_growth)
    terminal_value = fcf_terminal / (discount_rate - terminal_growth)
    pv_terminal = terminal_value / (1 + discount_rate) ** 5

    # Total intrinsic value
    total_value = pv_fcf + pv_terminal
    per_share_value = total_value / shares_outstanding if shares_outstanding > 0 else 0

    upside = (per_share_value - current_price) / current_price * 100 if current_price > 0 else 0

    if upside > 20:
        rec = "undervalued"
    elif upside > 0:
        rec = "fair_value"
    elif upside > -20:
        rec = "slightly_overvalued"
    else:
        rec = "overvalued"

    return round(per_share_value, 2), round(upside, 1), rec


def get_valuation(symbol):
    """
    Complete valuation analysis.
    Returns dict with PEG, DCF, and multi-quarter history summary.
    """
    result = {
        'pe': 0, 'growth_rate': 0, 'peg': None,
        'dcf_value': None, 'dcf_upside': None, 'dcf_rec': '',
        'history': [],
    }

    # Get PE from Tencent
    tencent_symbol = _tencent_symbol(symbol)
    url = "http://qt.gtimg.cn/q=" + tencent_symbol
    try:
        r = requests.get(url, timeout=5)
        text = r.text.strip().strip(';')
        if '~' in text:
            parts = text.split('~')
            result['pe'] = float(parts[39]) if len(parts) > 39 and parts[39] else 0
            result['price'] = float(parts[3]) if parts[3] else 0
    except Exception:
        pass

    # Get multi-quarter history
    history = get_multi_quarter_history(symbol)
    result['history'] = history

    # Calculate PEG
    if history:
        # Use the most recent growth rate
        latest_growth = history[0].get('growth', {})
        result['growth_rate'] = latest_growth.get('yoy_net_income', 0)

        if result['pe'] > 0 and result['growth_rate'] > 0:
            result['peg'] = calc_peg(result['pe'], result['growth_rate'])

    # Calculate DCF using real shares from baostock
    bs_sym = _bs_symbol(symbol)
    old_out, old_err = sys.stdout, sys.stderr
    devnull = open(os.devnull, 'w')
    try:
        sys.stdout = devnull
        sys.stderr = devnull
        lg2 = bs.login()
        if lg2.error_code == '0':
            # Get total shares
            rs_sh = bs.query_profit_data(code=bs_sym, year=2025, quarter=4)
            if rs_sh.error_code == '0' and rs_sh.next():
                row_sh = rs_sh.get_row_data()
                cols_sh = dict(zip(rs_sh.fields, row_sh))
                total_shares = float(cols_sh.get('totalShare', 0) or 0)

                if history and total_shares > 0:
                    net_profit = history[0]['quarters'].get('Q4', {}).get('net_profit', 0)
                    if net_profit == 0 and 'Q3' in history[0]['quarters']:
                        net_profit = history[0]['quarters']['Q3']['net_profit']

                    growth = result['growth_rate'] if result['growth_rate'] > 0 else 0.05

                    dcf_value, upside, rec = calc_dcf(
                        free_cash_flow=net_profit,
                        growth_rate=growth,
                        discount_rate=0.10,
                        terminal_growth=0.03,
                        shares_outstanding=total_shares,
                        current_price=result.get('price', 0)
                    )
                    result['dcf_value'] = dcf_value
                    result['dcf_upside'] = upside
                    result['dcf_rec'] = rec

            bs.logout()
    except Exception:
        pass
    finally:
        sys.stdout = old_out
        sys.stderr = old_err
        try:
            bs.logout()
        except:
            pass
        devnull.close()

    return result
