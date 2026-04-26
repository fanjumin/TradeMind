import requests
import baostock as bs
import os
import sys


def _bs_symbol(symbol):
    """Convert stock code to baostock format (e.g., 000001 -> sz.000001)"""
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
    """Convert stock code to Tencent format"""
    clean = symbol.replace('.SZ', '').replace('.SH', '').replace('.BJ', '')
    if clean.startswith('6'):
        return 'sh' + clean
    elif clean.startswith(('0', '3')):
        return 'sz' + clean
    else:
        return 'bj' + clean


def _bs_query(symbol, data_fn):
    """Query baostock data with suppressed login/logout output"""
    old_stdout = sys.stdout
    sys.stdout = open(os.devnull, 'w')
    try:
        lg = bs.login()
        if lg.error_code != '0':
            return {}

        results = {}
        bs_sym = _bs_symbol(symbol)

        # Profit data (latest annual)
        rs = bs.query_profit_data(code=bs_sym, year=2025, quarter=4)
        if rs.error_code == '0' and rs.next():
            row = rs.get_row_data()
            cols = dict(zip(rs.fields, row))
            results['roe'] = float(cols.get('roeAvg', 0) or 0)
            results['np_margin'] = float(cols.get('npMargin', 0) or 0)
            results['gp_margin'] = float(cols.get('gpMargin', 0) or 0) if cols.get('gpMargin') else 0
            results['eps_ttm'] = float(cols.get('epsTTM', 0) or 0)
            results['net_profit'] = float(cols.get('netProfit', 0) or 0)
            results['revenue'] = float(cols.get('MBRevenue', 0) or 0)

        # Growth data
        rs2 = bs.query_growth_data(code=bs_sym, year=2025, quarter=4)
        if rs2.error_code == '0' and rs2.next():
            row2 = rs2.get_row_data()
            cols2 = dict(zip(rs2.fields, row2))
            results['yoy_equity'] = float(cols2.get('YOYEquity', 0) or 0)
            results['yoy_net_income'] = float(cols2.get('YOYNI', 0) or 0)
            results['yoy_eps'] = float(cols2.get('YOYEPSBasic', 0) or 0)

        bs.logout()
        return results
    finally:
        sys.stdout.close()
        sys.stdout = old_stdout


def get_basic_info(symbol):
    """Get comprehensive fundamental data from Tencent + baostock"""
    results = {}

    # --- Tencent real-time data (fast, always available) ---
    tencent_symbol = _tencent_symbol(symbol)
    url = "http://qt.gtimg.cn/q=" + tencent_symbol
    try:
        r = requests.get(url, timeout=5)
        text = r.text.strip().strip(';')
        if '~' in text:
            parts = text.split('~')
            if len(parts) >= 50:
                results['company'] = parts[1]
                results['price'] = float(parts[3]) if parts[3] else 0
                results['prev_close'] = float(parts[4]) if parts[4] else 0
                results['turnover_rate'] = float(parts[38]) if len(parts) > 38 and parts[38] else 0
                results['pe_ttm'] = float(parts[39]) if len(parts) > 39 and parts[39] else 0
                results['amplitude'] = float(parts[46]) if len(parts) > 46 and parts[46] else 0
                results['net_asset_per_share'] = float(parts[47]) if len(parts) > 47 and parts[47] else 0
                results['volume_ratio'] = float(parts[53]) if len(parts) > 53 and parts[53] else 0
                results['high_52w'] = float(parts[62]) if len(parts) > 62 and parts[62] else 0
                results['low_52w'] = float(parts[63]) if len(parts) > 63 and parts[63] else 0

                # PB = price / net_asset_per_share
                if results['net_asset_per_share'] > 0:
                    results['pb'] = results['price'] / results['net_asset_per_share']
    except Exception:
        pass

    # --- Baostock financial data (ROE, margins, growth) ---
    try:
        bs_data = _bs_query(symbol, 'profit+growth')
        results.update(bs_data)
    except Exception:
        pass

    return results


def get_basic_score(info):
    """
    Comprehensive fundamental scoring (0-100)

    Components:
      PE (15pts)  - Valuation reasonableness
      PB (10pts)  - Price-to-book reasonableness
      ROE (25pts) - Return on equity (Buffett's favorite)
      Profit Margin (15pts) - Net profit margin quality
      Growth (20pts) - Revenue & profit growth
      Turnover activity (10pts) - Trading activity health
    """
    score = 0
    reasons = []

    # === 1. PE Ratio (15 pts) ===
    pe = info.get('pe_ttm', 0)
    if 0 < pe < 15:
        score += 15
        reasons.append('估值便宜(PE<15)')
    elif 15 <= pe < 25:
        score += 12
        reasons.append('估值合理(PE 15-25)')
    elif 25 <= pe < 40:
        score += 8
        reasons.append('估值偏高(PE 25-40)')
    elif 40 <= pe < 60:
        score += 3
        reasons.append('估值过高(PE 40-60)')
    elif pe >= 60:
        reasons.append('估值泡沫(PE>60)')
    else:
        reasons.append('无PE数据')

    # === 2. PB Ratio (10 pts) ===
    pb = info.get('pb', 0)
    if 0 < pb < 1.5:
        score += 10
        reasons.append('市净率极低(PB<1.5)')
    elif 1.5 <= pb < 3:
        score += 8
        reasons.append('市净率合理(PB 1.5-3)')
    elif 3 <= pb < 6:
        score += 5
        reasons.append('市净率偏高')
    elif pb >= 6:
        score += 1
        reasons.append('市净率过高')

    # === 3. ROE (25 pts) - The most important metric ===
    roe = info.get('roe', 0)
    if roe >= 0.20:
        score += 25
        reasons.append('ROE优秀(>=%.0f%%)' % (roe * 100))
    elif roe >= 0.15:
        score += 20
        reasons.append('ROE良好(%.0f%%)' % (roe * 100))
    elif roe >= 0.10:
        score += 15
        reasons.append('ROE合格(%.0f%%)' % (roe * 100))
    elif roe >= 0.05:
        score += 8
        reasons.append('ROE偏低(%.0f%%)' % (roe * 100))
    elif roe > 0:
        score += 3
        reasons.append('ROE较弱(%.0f%%)' % (roe * 100))
    else:
        reasons.append('亏损(ROE<0)')

    # === 4. Net Profit Margin (15 pts) ===
    npm = info.get('np_margin', 0)
    if npm >= 0.30:
        score += 15
        reasons.append('净利率极高(%.1f%%)' % (npm * 100))
    elif npm >= 0.15:
        score += 12
        reasons.append('净利率优秀(%.1f%%)' % (npm * 100))
    elif npm >= 0.08:
        score += 8
        reasons.append('净利率良好(%.1f%%)' % (npm * 100))
    elif npm >= 0.03:
        score += 4
        reasons.append('净利率一般(%.1f%%)' % (npm * 100))
    else:
        score += 1
        reasons.append('净利率偏低(%.1f%%)' % (npm * 100))

    # === 5. Growth (20 pts) - Combined YOY growth ===
    yoy_ni = info.get('yoy_net_income', 0)
    yoy_eps = info.get('yoy_eps', 0)
    growth_score = 0

    # Net income growth (10 pts)
    if yoy_ni >= 0.30:
        growth_score += 10
    elif yoy_ni >= 0.15:
        growth_score += 8
    elif yoy_ni >= 0:
        growth_score += 5
    elif yoy_ni >= -0.10:
        growth_score += 2
    else:
        growth_score += 0

    # EPS growth (10 pts)
    if yoy_eps >= 0.20:
        growth_score += 10
    elif yoy_eps >= 0.10:
        growth_score += 8
    elif yoy_eps >= 0:
        growth_score += 5
    elif yoy_eps >= -0.10:
        growth_score += 2
    else:
        growth_score += 0

    score += growth_score
    if growth_score >= 15:
        reasons.append('高增长(净利+%.1f%%)' % (yoy_ni * 100))
    elif growth_score >= 8:
        reasons.append('温和增长(净利%+.1f%%)' % (yoy_ni * 100))
    elif growth_score >= 3:
        reasons.append('增长停滞(净利%+.1f%%)' % (yoy_ni * 100))
    else:
        reasons.append('负增长(净利%.1f%%)' % (yoy_ni * 100))

    # === 6. Turnover activity (10 pts) ===
    tr = info.get('turnover_rate', 0)
    if 1.0 <= tr <= 5.0:
        score += 10
        reasons.append('交投活跃(换手率%.1f%%)' % tr)
    elif 5.0 < tr <= 10.0:
        score += 8
        reasons.append('交投较热(换手率%.1f%%)' % tr)
    elif 0.3 <= tr < 1.0:
        score += 6
        reasons.append('交投清淡(换手率%.1f%%)' % tr)
    elif tr > 10.0:
        score += 5
        reasons.append('交投过热(换手率%.1f%%)' % tr)
    else:
        score += 2
        reasons.append('交投极冷(换手率%.1f%%)' % tr)

    # === Bonus context ===
    company = info.get('company', '')
    if company:
        reasons.append('标的: ' + company)

    return min(int(score), 100), reasons


if __name__ == "__main__":
    # Quick test
    for sym in ['000001', '600519']:
        info = get_basic_info(sym)
        score, reasons = get_basic_score(info)
        print(f"\n{sym} ({info.get('company', '?')}):")
        print(f"  Score: {score}/100")
        print(f"  PE: {info.get('pe_ttm', 'N/A')}  PB: {info.get('pb', 'N/A')}")
        print(f"  ROE: {info.get('roe', 'N/A')}  NetMargin: {info.get('np_margin', 'N/A')}")
        print(f"  YOY NI: {info.get('yoy_net_income', 'N/A')}  YOY EPS: {info.get('yoy_eps', 'N/A')}")
        for r in reasons:
            print(f"  - {r}")
