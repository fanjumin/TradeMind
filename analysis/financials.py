"""
TradeMind Financial Data Engine — 对标同花顺/东方财富三表分析
使用 baostock 获取: 利润表 + 资产负债表 + 现金流 + 成长性
计算: ROE/ROA/毛利率/净利率/营收增长率/负债率/现金流质量等
"""
import os, json, time
from datetime import datetime
from collections import defaultdict

try:
    import baostock as bs
    import pandas as pd
    import numpy as np
except ImportError as e:
    print(f"[financials] Missing dependency: {e}")
    raise

# Cache directory
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'financials')
os.makedirs(CACHE_DIR, exist_ok=True)

# ============================================================
# Data Fetching
# ============================================================

def _ensure_login():
    """Ensure baostock is logged in."""
    bs.login()

def _ensure_logout():
    """Logout from baostock."""
    try:
        bs.logout()
    except:
        pass

def _symbol_to_baostock(symbol):
    """Convert symbol like '600519' to baostock format 'sh.600519'."""
    code = str(symbol).zfill(6)
    if code.startswith(('6', '9')):
        return f'sh.{code}'
    elif code.startswith(('0', '3', '2')):
        return f'sz.{code}'
    return f'sz.{code}'

def _safe_float(val, default=0.0):
    """Convert value to float safely."""
    if val is None or val == '' or val == 'None':
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def fetch_financial_data(symbol, years=3):
    """
    Fetch comprehensive financial data for a stock.
    Returns dict with profit, balance, cashflow, growth data for multiple periods.
    Cache results to disk.
    """
    sym = str(symbol).zfill(6)
    bs_code = _symbol_to_baostock(sym)
    
    # Check cache
    cache_file = os.path.join(CACHE_DIR, f'{sym}.json')
    if os.path.exists(cache_file):
        mtime = os.path.getmtime(cache_file)
        if time.time() - mtime < 86400:  # 24h cache
            try:
                with open(cache_file) as f:
                    cached = json.load(f)
                if cached.get('symbol') == sym:
                    return cached
            except:
                pass

    _ensure_login()
    
    result = {
        'symbol': sym,
        'baostock_code': bs_code,
        'fetched_at': datetime.now().isoformat(),
        'quarters': []
    }
    
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    for year_offset in range(years):
        year = current_year - year_offset
        max_quarter = 4 if year < current_year else ((current_month - 1) // 3 + 1)
        
        for q in range(max_quarter, 0, -1):
            quarter_data = {'year': year, 'quarter': q, 'stat_date': f'{year}-{q*3:02d}-{q*3:02d}' if q < 4 else f'{year}-12-31'}
            
            try:
                # Profit data
                rs_profit = bs.query_profit_data(code=bs_code, year=year, quarter=q)
                if rs_profit.error_code == '0':
                    while rs_profit.next():
                        row = rs_profit.get_row_data()
                        fields = rs_profit.fields
                        d = dict(zip(fields, row))
                        quarter_data['profit'] = {
                            'roe': _safe_float(d.get('roeAvg')),
                            'net_margin': _safe_float(d.get('npMargin')),
                            'gross_margin': _safe_float(d.get('gpMargin')),
                            'net_profit': _safe_float(d.get('netProfit')),
                            'eps': _safe_float(d.get('epsTTM')),
                            'revenue': _safe_float(d.get('MBRevenue')),
                            'total_shares': _safe_float(d.get('totalShare')),
                        }
                
                # Balance data
                rs_balance = bs.query_balance_data(code=bs_code, year=year, quarter=q)
                if rs_balance.error_code == '0':
                    while rs_balance.next():
                        row = rs_balance.get_row_data()
                        fields = rs_balance.fields
                        d = dict(zip(fields, row))
                        quarter_data['balance'] = {
                            'current_ratio': _safe_float(d.get('currentRatio')),
                            'quick_ratio': _safe_float(d.get('quickRatio')),
                            'cash_ratio': _safe_float(d.get('cashRatio')),
                            'debt_to_asset': _safe_float(d.get('liabilityToAsset')),
                            'equity_multiplier': _safe_float(d.get('assetToEquity')),
                            'yoy_liability': _safe_float(d.get('YOYLiability')),
                        }
                
                # Cash flow data
                rs_cf = bs.query_cash_flow_data(code=bs_code, year=year, quarter=q)
                if rs_cf.error_code == '0':
                    while rs_cf.next():
                        row = rs_cf.get_row_data()
                        fields = rs_cf.fields
                        d = dict(zip(fields, row))
                        quarter_data['cashflow'] = {
                            'cfo_to_revenue': _safe_float(d.get('CFOToOR')),
                            'cfo_to_profit': _safe_float(d.get('CFOToNP')),
                            'cfo_to_assets': _safe_float(d.get('CFOToGr')),
                            'ca_to_asset': _safe_float(d.get('CAToAsset')),
                        }
                
                # Growth data
                rs_growth = bs.query_growth_data(code=bs_code, year=year, quarter=q)
                if rs_growth.error_code == '0':
                    while rs_growth.next():
                        row = rs_growth.get_row_data()
                        fields = rs_growth.fields
                        d = dict(zip(fields, row))
                        quarter_data['growth'] = {
                            'yoy_equity': _safe_float(d.get('YOYEquity')),
                            'yoy_asset': _safe_float(d.get('YOYAsset')),
                            'yoy_net_income': _safe_float(d.get('YOYNI')),
                            'yoy_eps': _safe_float(d.get('YOYEPSBasic')),
                        }
            except Exception as e:
                quarter_data['error'] = str(e)
            
            if 'profit' in quarter_data or 'balance' in quarter_data:
                result['quarters'].append(quarter_data)
    
    _ensure_logout()
    
    # Cache to disk
    try:
        with open(cache_file, 'w') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    except:
        pass
    
    return result


# ============================================================
# Financial Metrics Computation
# ============================================================

def compute_financial_metrics(fin_data):
    """
    Compute comprehensive financial metrics from raw data.
    Returns structured metrics with trends and scores.
    """
    quarters = fin_data.get('quarters', [])
    if not quarters:
        return {'error': 'No financial data available'}
    
    metrics = {
        'symbol': fin_data['symbol'],
        'periods': len(quarters),
        'latest': {},
        'trends': {},
        'scores': {},
        'summary': '',
    }
    
    # Extract latest quarter data
    latest = quarters[0] if quarters else {}
    
    # === Profitability ===
    profit_data = [q.get('profit', {}) for q in quarters if 'profit' in q]
    if profit_data:
        latest_p = profit_data[0]
        metrics['latest']['roe'] = latest_p.get('roe', 0)
        metrics['latest']['net_margin'] = latest_p.get('net_margin', 0)
        metrics['latest']['gross_margin'] = latest_p.get('gross_margin', 0)
        metrics['latest']['eps'] = latest_p.get('eps', 0)
        metrics['latest']['revenue'] = latest_p.get('revenue', 0)
        metrics['latest']['net_profit'] = latest_p.get('net_profit', 0)
        
        # ROE trend (last 4 quarters)
        roes = [p.get('roe', 0) for p in profit_data[:4] if p.get('roe')]
        if len(roes) >= 2:
            metrics['trends']['roe'] = {
                'current': roes[0],
                'prev': roes[1],
                'change': roes[0] - roes[1],
                'direction': 'up' if roes[0] > roes[1] else 'down' if roes[0] < roes[1] else 'flat'
            }
        
        # Revenue growth trend
        revenues = [p.get('revenue', 0) for p in profit_data[:4] if p.get('revenue')]
        if len(revenues) >= 2:
            rev_growth = (revenues[0] / revenues[1] - 1) if revenues[1] else 0
            metrics['trends']['revenue_growth'] = {
                'current': revenues[0],
                'prev': revenues[1],
                'growth_rate': rev_growth,
                'direction': 'up' if rev_growth > 0 else 'down'
            }
    
    # === Financial Health ===
    balance_data = [q.get('balance', {}) for q in quarters if 'balance' in q]
    if balance_data:
        latest_b = balance_data[0]
        metrics['latest']['current_ratio'] = latest_b.get('current_ratio', 0)
        metrics['latest']['quick_ratio'] = latest_b.get('quick_ratio', 0)
        metrics['latest']['debt_to_asset'] = latest_b.get('debt_to_asset', 0)
        metrics['latest']['equity_multiplier'] = latest_b.get('equity_multiplier', 0)
    
    # === Cash Flow Quality ===
    cf_data = [q.get('cashflow', {}) for q in quarters if 'cashflow' in q]
    if cf_data:
        latest_cf = cf_data[0]
        metrics['latest']['cfo_to_profit'] = latest_cf.get('cfo_to_profit', 0)
        metrics['latest']['cfo_to_revenue'] = latest_cf.get('cfo_to_revenue', 0)
    
    # === Growth ===
    growth_data = [q.get('growth', {}) for q in quarters if 'growth' in q]
    if growth_data:
        latest_g = growth_data[0]
        metrics['latest']['yoy_net_income_growth'] = latest_g.get('yoy_net_income', 0)
        metrics['latest']['yoy_eps_growth'] = latest_g.get('yoy_eps', 0)
        metrics['latest']['yoy_equity_growth'] = latest_g.get('yoy_equity', 0)
    
    # === Scoring (100-point scale) ===
    scores = {}
    
    # ROE score (0-25)
    roe = metrics['latest'].get('roe', 0)
    if roe >= 0.20: scores['roe'] = 25
    elif roe >= 0.15: scores['roe'] = 20
    elif roe >= 0.10: scores['roe'] = 15
    elif roe >= 0.05: scores['roe'] = 10
    elif roe > 0: scores['roe'] = 5
    else: scores['roe'] = 0
    
    # Gross margin score (0-15)
    gm = metrics['latest'].get('gross_margin', 0)
    if gm >= 0.60: scores['gross_margin'] = 15
    elif gm >= 0.40: scores['gross_margin'] = 12
    elif gm >= 0.20: scores['gross_margin'] = 8
    elif gm > 0: scores['gross_margin'] = 4
    else: scores['gross_margin'] = 0
    
    # Debt health (0-15) — lower is better
    debt = metrics['latest'].get('debt_to_asset', 1)
    if debt <= 0.30: scores['debt'] = 15
    elif debt <= 0.50: scores['debt'] = 12
    elif debt <= 0.70: scores['debt'] = 8
    elif debt <= 0.85: scores['debt'] = 4
    else: scores['debt'] = 0
    
    # Cash flow quality (0-15)
    cfo = metrics['latest'].get('cfo_to_profit', 0)
    if cfo >= 1.0: scores['cashflow'] = 15
    elif cfo >= 0.7: scores['cashflow'] = 12
    elif cfo >= 0.4: scores['cashflow'] = 8
    elif cfo > 0: scores['cashflow'] = 4
    else: scores['cashflow'] = 0
    
    # Growth (0-15)
    yoy = metrics['latest'].get('yoy_net_income_growth', 0)
    if yoy >= 0.30: scores['growth'] = 15
    elif yoy >= 0.15: scores['growth'] = 12
    elif yoy >= 0.05: scores['growth'] = 8
    elif yoy > 0: scores['growth'] = 4
    else: scores['growth'] = 0
    
    # Liquidity (0-15)
    cr = metrics['latest'].get('current_ratio', 0)
    if cr >= 3.0: scores['liquidity'] = 15
    elif cr >= 2.0: scores['liquidity'] = 12
    elif cr >= 1.0: scores['liquidity'] = 8
    elif cr > 0: scores['liquidity'] = 4
    else: scores['liquidity'] = 0
    
    total_score = sum(scores.values())
    metrics['scores'] = {'breakdown': scores, 'total': total_score, 'max': 100}
    
    # Summary
    if total_score >= 80:
        metrics['summary'] = '优秀 — 财务健康，盈利能力强劲，建议重点关注'
    elif total_score >= 60:
        metrics['summary'] = '良好 — 财务稳健，多数指标健康'
    elif total_score >= 40:
        metrics['summary'] = '一般 — 存在部分财务风险，需关注'
    elif total_score >= 20:
        metrics['summary'] = '较差 — 多项财务指标不理想，谨慎对待'
    else:
        metrics['summary'] = '差 — 财务状况堪忧，建议回避'
    
    return metrics


def analyze_financials(symbol, years=3):
    """
    One-stop financial analysis: fetch + compute + score.
    Returns comprehensive financial analysis result.
    """
    data = fetch_financial_data(symbol, years=years)
    if not data.get('quarters'):
        return {'error': f'No financial data for {symbol}', 'symbol': symbol}
    
    metrics = compute_financial_metrics(data)
    return {
        'symbol': symbol,
        'fetched_at': data.get('fetched_at'),
        'quarters_count': len(data['quarters']),
        'metrics': metrics,
    }


def print_financial_report(symbol):
    """Print a formatted financial analysis report."""
    result = analyze_financials(symbol)
    if 'error' in result:
        print(f"❌ {result['error']}")
        return
    
    m = result['metrics']
    
    print(f"\n{'='*60}")
    print(f"  📊 {symbol} 财务分析报告")
    print(f"  📅 数据截至: {result.get('fetched_at', 'N/A')[:10]}")
    print(f"  📈 分析周期: {result['quarters_count']} 个季度")
    print(f"{'='*60}")
    
    print(f"\n  💰 盈利能力:")
    print(f"     ROE (净资产收益率): {m['latest'].get('roe', 0)*100:.1f}%")
    print(f"     毛利率:             {m['latest'].get('gross_margin', 0)*100:.1f}%")
    print(f"     净利率:             {m['latest'].get('net_margin', 0)*100:.1f}%")
    print(f"     EPS:               {m['latest'].get('eps', 0):.2f}")
    
    print(f"\n  🏦 财务健康:")
    print(f"     流动比率:           {m['latest'].get('current_ratio', 0):.2f}")
    print(f"     速动比率:           {m['latest'].get('quick_ratio', 0):.2f}")
    print(f"     资产负债率:         {m['latest'].get('debt_to_asset', 0)*100:.1f}%")
    
    print(f"\n  💵 现金流:")
    print(f"     经营现金流/净利润:  {m['latest'].get('cfo_to_profit', 0):.2f}")
    print(f"     经营现金流/营收:    {m['latest'].get('cfo_to_revenue', 0):.2f}")
    
    print(f"\n  📈 成长性:")
    print(f"     净利润同比增长:     {m['latest'].get('yoy_net_income_growth', 0)*100:.1f}%")
    print(f"     EPS同比增长:       {m['latest'].get('yoy_eps_growth', 0)*100:.1f}%")
    
    print(f"\n  🎯 综合评分: {m['scores']['total']}/100")
    s = m['scores']['breakdown']
    print(f"     ROE: {s.get('roe',0)}/25 | 毛利率: {s.get('gross_margin',0)}/15 | 负债: {s.get('debt',0)}/15")
    print(f"     现金流: {s.get('cashflow',0)}/15 | 成长: {s.get('growth',0)}/15 | 流动性: {s.get('liquidity',0)}/15")
    
    print(f"\n  📝 {m['summary']}")
    print(f"{'='*60}\n")


# CLI entry
if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        print_financial_report(sys.argv[1])
    else:
        # Test with 600519
        print_financial_report('600519')
