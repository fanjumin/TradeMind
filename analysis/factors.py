"""
TradeMind Factor Analysis Framework — 对标米筐/聚宽因子研究平台
支持: IC/IR分析 + 分层回测(quintile) + 因子相关性矩阵 + 因子衰减
因子库: 估值/动量/质量/波动/规模/流动性 6大类
"""
import os, json, time
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np
from scipy import stats

try:
    import baostock as bs
    import pandas as pd
except ImportError as e:
    print(f"[factors] Missing dependency: {e}")
    raise

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'factors')
os.makedirs(CACHE_DIR, exist_ok=True)

# ============================================================
# Factor Definitions
# ============================================================

FACTOR_DEFS = {
    'pe':        {'name': '市盈率', 'category': '估值', 'direction': -1},  # 越低越好
    'pb':        {'name': '市净率', 'category': '估值', 'direction': -1},
    'roe':       {'name': 'ROE', 'category': '质量', 'direction': 1},       # 越高越好
    'gross_margin': {'name': '毛利率', 'category': '质量', 'direction': 1},
    'net_margin':   {'name': '净利率', 'category': '质量', 'direction': 1},
    'debt_ratio':   {'name': '资产负债率', 'category': '质量', 'direction': -1},
    'momentum_1m':  {'name': '1月动量', 'category': '动量', 'direction': 1},
    'momentum_3m':  {'name': '3月动量', 'category': '动量', 'direction': 1},
    'rsi_14':       {'name': 'RSI(14)', 'category': '动量', 'direction': -1},  # 超买不好
    'volatility':   {'name': '波动率', 'category': '波动', 'direction': -1},
    'turnover':     {'name': '换手率', 'category': '流动性', 'direction': 1},   # 适度流动性
    'market_cap':   {'name': '市值', 'category': '规模', 'direction': -1},     # 小盘效应
}

# ============================================================
# Factor Computation
# ============================================================

def _ensure_login():
    try: bs.login()
    except: pass

def _ensure_logout():
    try: bs.logout()
    except: pass

def _symbol_to_baostock(symbol):
    code = str(symbol).zfill(6)
    return f'sh.{code}' if code.startswith(('6','9')) else f'sz.{code}'

def compute_factors_for_stock(symbol, days_back=365):
    """
    Compute all factor values for a single stock.
    Returns dict of factor_name -> value.
    """
    sym = str(symbol).zfill(6)
    bs_code = _symbol_to_baostock(sym)
    
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days_back+100)).strftime('%Y-%m-%d')
    
    factors = {'symbol': sym}
    
    _ensure_login()
    
    try:
        # Get K-line data for price-based factors
        rs = bs.query_history_k_data_plus(
            bs_code, "date,close,volume,amount,turn,peTTM,pbMRQ",
            start_date=start_date, end_date=end_date,
            frequency="d", adjustflag="2"
        )
        
        if rs.error_code != '0':
            _ensure_logout()
            return factors
        
        data = []
        while rs.next():
            data.append(rs.get_row_data())
        
        if not data:
            _ensure_logout()
            return factors
        
        df = pd.DataFrame(data, columns=rs.fields)
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df['turn'] = pd.to_numeric(df['turn'], errors='coerce')
        df['peTTM'] = pd.to_numeric(df['peTTM'], errors='coerce')
        df['pbMRQ'] = pd.to_numeric(df['pbMRQ'], errors='coerce')
        df = df.dropna(subset=['close'])
        
        if len(df) < 20:
            _ensure_logout()
            return factors
        
        latest = df.iloc[-1]
        closes = df['close'].values
        
        # PE / PB
        factors['pe'] = float(latest['peTTM']) if pd.notna(latest['peTTM']) and latest['peTTM'] > 0 else None
        factors['pb'] = float(latest['pbMRQ']) if pd.notna(latest['pbMRQ']) and latest['pbMRQ'] > 0 else None
        
        # Momentum factors
        if len(closes) >= 21:
            factors['momentum_1m'] = float(closes[-1] / closes[-21] - 1)
        if len(closes) >= 63:
            factors['momentum_3m'] = float(closes[-1] / closes[-63] - 1)
        
        # RSI(14)
        if len(closes) >= 15:
            deltas = np.diff(closes[-15:])
            gains = np.sum(deltas[deltas > 0]) if np.any(deltas > 0) else 0
            losses = -np.sum(deltas[deltas < 0]) if np.any(deltas < 0) else 1e-10
            rs_val = gains / losses if losses > 0 else 100
            factors['rsi_14'] = float(100 - 100 / (1 + rs_val))
        
        # Volatility (annualized, 60-day)
        if len(closes) >= 60:
            returns = np.diff(np.log(closes[-61:]))
            factors['volatility'] = float(np.std(returns) * np.sqrt(252))
        
        # Turnover
        factors['turnover'] = float(latest['turn']) if pd.notna(latest['turn']) else None
        
        # Market cap (from PE * earnings — approximate)
        if factors.get('pe') and factors.get('pe') > 0:
            # Approximate: use close price as proxy for total market value
            factors['market_cap'] = float(latest['close']) * 1e8  # rough approximation
        
        # Get financial factors from baostock
        try:
            rs_profit = bs.query_profit_data(code=bs_code, year=datetime.now().year, quarter=1)
            if rs_profit.error_code == '0':
                while rs_profit.next():
                    row = rs_profit.get_row_data()
                    d = dict(zip(rs_profit.fields, row))
                    factors['roe'] = float(d.get('roeAvg', 0)) if d.get('roeAvg') else None
                    factors['gross_margin'] = float(d.get('gpMargin', 0)) if d.get('gpMargin') else None
                    factors['net_margin'] = float(d.get('npMargin', 0)) if d.get('npMargin') else None
        except:
            pass
        
        try:
            rs_bal = bs.query_balance_data(code=bs_code, year=datetime.now().year, quarter=1)
            if rs_bal.error_code == '0':
                while rs_bal.next():
                    row = rs_bal.get_row_data()
                    d = dict(zip(rs_bal.fields, row))
                    factors['debt_ratio'] = float(d.get('liabilityToAsset', 0)) if d.get('liabilityToAsset') else None
        except:
            pass
    
    except Exception as e:
        factors['_error'] = str(e)
    finally:
        _ensure_logout()
    
    return factors


# ============================================================
# IC Analysis (Information Coefficient)
# ============================================================

def compute_ic(factor_values, forward_returns):
    """
    Compute Spearman rank IC between factor values and forward returns.
    
    Args:
        factor_values: dict {symbol: factor_value}
        forward_returns: dict {symbol: forward_return}
    
    Returns:
        dict with ic, t_stat, p_value
    """
    symbols = list(set(factor_values.keys()) & set(forward_returns.keys()))
    if len(symbols) < 10:
        return {'ic': 0, 't_stat': 0, 'p_value': 1, 'n': len(symbols), 'error': 'Insufficient samples'}
    
    x = np.array([factor_values[s] for s in symbols])
    y = np.array([forward_returns[s] for s in symbols])
    
    # Remove NaN
    mask = ~(np.isnan(x) | np.isnan(y))
    x, y = x[mask], y[mask]
    
    if len(x) < 10:
        return {'ic': 0, 't_stat': 0, 'p_value': 1, 'n': len(x), 'error': 'Insufficient valid samples'}
    
    # Spearman rank correlation
    ic, p_value = stats.spearmanr(x, y)
    
    # T-statistic
    n = len(x)
    if abs(ic) >= 1.0:
        t_stat = float('inf')
    else:
        t_stat = ic * np.sqrt((n - 2) / (1 - ic**2))
    
    return {
        'ic': round(float(ic), 4),
        't_stat': round(float(t_stat), 2),
        'p_value': round(float(p_value), 4),
        'n': n,
        'significant': p_value < 0.05,
    }


def compute_all_factor_ics(stock_universe, forward_days=20):
    """
    Compute IC for all factors across a stock universe.
    
    Args:
        stock_universe: list of stock symbols (e.g., ['000001', '600519', ...])
        forward_days: forward return period
    
    Returns:
        dict of factor_name -> IC result
    """
    factor_data = {}  # factor_name -> {symbol: value}
    forward_returns = {}  # symbol -> forward return
    
    for i, symbol in enumerate(stock_universe):
        if i % 20 == 0:
            print(f"  Processing {i+1}/{len(stock_universe)}...")
        
        factors = compute_factors_for_stock(symbol, days_back=252)
        
        # Collect factor values
        for fname in FACTOR_DEFS:
            if fname in factors and factors[fname] is not None:
                if fname not in factor_data:
                    factor_data[fname] = {}
                factor_data[fname][symbol] = factors[fname]
        
        # Compute forward return
        sym = str(symbol).zfill(6)
        bs_code = _symbol_to_baostock(sym)
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=forward_days+30)).strftime('%Y-%m-%d')
        
        _ensure_login()
        try:
            rs = bs.query_history_k_data_plus(
                bs_code, "date,close", start_date=start_date, end_date=end_date,
                frequency="d", adjustflag="2"
            )
            closes = []
            while rs.next():
                closes.append(rs.get_row_data()[1])
            if len(closes) >= forward_days + 1:
                start_price = float(closes[0])
                end_price = float(closes[-1])
                if start_price > 0:
                    forward_returns[symbol] = end_price / start_price - 1
        except:
            pass
        _ensure_logout()
    
    # Compute IC for each factor
    results = {}
    for fname, values in factor_data.items():
        ic_result = compute_ic(values, forward_returns)
        ic_result['category'] = FACTOR_DEFS[fname]['category']
        ic_result['name'] = FACTOR_DEFS[fname]['name']
        results[fname] = ic_result
    
    return results


# ============================================================
# Stratified Backtest (分层回测)
# ============================================================

def stratified_backtest(factor_name, stock_universe, n_groups=5):
    """
    Perform stratified backtest: group stocks by factor into n_groups,
    compute average forward return for each group.
    
    Args:
        factor_name: which factor to stratify by
        stock_universe: list of symbols
        n_groups: number of quantile groups
    
    Returns:
        dict with group returns and monotonicity check
    """
    factor_values = {}
    forward_returns = {}
    
    for i, symbol in enumerate(stock_universe):
        factors = compute_factors_for_stock(symbol)
        if factor_name in factors and factors[factor_name] is not None:
            factor_values[symbol] = factors[factor_name]
        
        # Forward 20-day return
        sym = str(symbol).zfill(6)
        bs_code = _symbol_to_baostock(sym)
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=50)).strftime('%Y-%m-%d')
        
        _ensure_login()
        try:
            rs = bs.query_history_k_data_plus(
                bs_code, "date,close", start_date=start_date, end_date=end_date,
                frequency="d", adjustflag="2"
            )
            closes = []
            while rs.next():
                closes.append(rs.get_row_data()[1])
            if len(closes) >= 21:
                forward_returns[symbol] = float(closes[-1]) / float(closes[-21]) - 1
        except:
            pass
        _ensure_logout()
    
    symbols = list(set(factor_values.keys()) & set(forward_returns.keys()))
    if len(symbols) < n_groups * 3:
        return {'error': f'Insufficient samples: {len(symbols)}'}
    
    # Sort by factor value
    direction = FACTOR_DEFS.get(factor_name, {}).get('direction', 1)
    sorted_symbols = sorted(symbols, key=lambda s: factor_values[s] * direction)
    
    # Split into groups
    group_size = len(sorted_symbols) // n_groups
    groups = []
    for g in range(n_groups):
        start = g * group_size
        end = start + group_size if g < n_groups - 1 else len(sorted_symbols)
        group_symbols = sorted_symbols[start:end]
        avg_return = np.mean([forward_returns[s] for s in group_symbols])
        avg_factor = np.mean([factor_values[s] for s in group_symbols])
        groups.append({
            'group': g + 1,
            'label': f'Q{g+1}' if direction > 0 else f'Q{n_groups-g}',
            'n_stocks': len(group_symbols),
            'avg_return': round(float(avg_return) * 100, 2),
            'avg_factor': round(float(avg_factor), 4),
        })
    
    # Monotonicity check
    returns = [g['avg_return'] for g in groups]
    if direction > 0:
        monotonic = all(returns[i] <= returns[i+1] for i in range(len(returns)-1))
        spread = returns[-1] - returns[0]
    else:
        monotonic = all(returns[i] >= returns[i+1] for i in range(len(returns)-1))
        spread = returns[0] - returns[-1]
    
    return {
        'factor': factor_name,
        'factor_name': FACTOR_DEFS.get(factor_name, {}).get('name', factor_name),
        'category': FACTOR_DEFS.get(factor_name, {}).get('category', ''),
        'n_stocks': len(symbols),
        'n_groups': n_groups,
        'groups': groups,
        'spread_pct': round(spread, 2),
        'monotonic': monotonic,
        'alpha_signal': monotonic and abs(spread) > 1.0,
    }


# ============================================================
# Factor Correlation Matrix
# ============================================================

def compute_factor_correlation(stock_universe):
    """
    Compute pairwise correlation matrix of all factors.
    
    Returns:
        dict with correlation matrix and cluster suggestions
    """
    # Collect all factor values
    factor_matrix = defaultdict(dict)  # symbol -> {factor: value}
    
    for symbol in stock_universe:
        factors = compute_factors_for_stock(symbol)
        for fname in FACTOR_DEFS:
            if fname in factors and factors[fname] is not None:
                factor_matrix[symbol][fname] = factors[fname]
    
    # Build DataFrame
    data = []
    factor_names = list(FACTOR_DEFS.keys())
    for symbol, fvals in factor_matrix.items():
        row = [fvals.get(f, np.nan) for f in factor_names]
        if sum(1 for v in row if not np.isnan(v)) >= len(factor_names) * 0.5:
            data.append(row)
    
    if len(data) < 5:
        return {'error': 'Insufficient data for correlation'}
    
    df = pd.DataFrame(data, columns=factor_names)
    corr_matrix = df.corr()
    
    # Build result
    correlations = {}
    for i, f1 in enumerate(factor_names):
        for j, f2 in enumerate(factor_names):
            if i < j:
                val = corr_matrix.iloc[i, j]
                if pd.notna(val):
                    correlations[f'{f1}_vs_{f2}'] = {
                        'factor1': FACTOR_DEFS[f1]['name'],
                        'factor2': FACTOR_DEFS[f2]['name'],
                        'correlation': round(float(val), 3),
                        'abs_corr': round(abs(float(val)), 3),
                    }
    
    # Find highly correlated pairs
    high_corr = [(k, v) for k, v in correlations.items() 
                 if v['abs_corr'] > 0.7]
    
    # Cluster suggestions
    if high_corr:
        # Simple: group by checking transitivity
        clusters = []
        used = set()
        for key, val in high_corr:
            f1, f2 = key.split('_vs_')
            if f1 not in used and f2 not in used:
                clusters.append({'factors': [f1, f2], 'correlation': val['correlation']})
                used.add(f1)
                used.add(f2)
    
    return {
        'n_samples': len(data),
        'factor_count': len(factor_names),
        'pairs': len(correlations),
        'correlations': correlations,
        'high_correlation_pairs': [{'pair': k, **v} for k, v in high_corr],
    }


# ============================================================
# Full Factor Report
# ============================================================

def full_factor_analysis(stock_universe=None, forward_days=20):
    """
    Run complete factor analysis: IC + stratified backtest + correlation.
    
    Args:
        stock_universe: list of symbols, or None for default set
        forward_days: forward return period for IC
    """
    if stock_universe is None:
        # Default: major index constituents
        stock_universe = [
            '600519', '000858', '000001', '600036', '601318', '600276',
            '000333', '002594', '300750', '600900', '601166', '002475',
            '601012', '002230', '688981', '002049', '300059', '600030',
            '000725', '601899', '600809', '000568', '600887', '601088',
        ]
    
    print(f"\n{'='*60}")
    print(f"  📊 因子分析报告")
    print(f"  📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  📈 样本数量: {len(stock_universe)} stocks")
    print(f"  ⏱ 前瞻期: {forward_days} 天")
    print(f"{'='*60}")
    
    # 1. IC Analysis
    print(f"\n  --- IC 分析 (Spearman Rank) ---")
    ic_results = compute_all_factor_ics(stock_universe, forward_days)
    
    # Sort by absolute IC
    sorted_ic = sorted(ic_results.items(), key=lambda x: abs(x[1]['ic']), reverse=True)
    
    print(f"  {'因子':<16} {'类别':<8} {'IC':>8} {'T值':>8} {'显著':>6} {'N':>6}")
    print(f"  {'-'*58}")
    sig_factors = []
    for fname, r in sorted_ic:
        sig = '✅' if r.get('significant') else '  '
        if r.get('significant'):
            sig_factors.append(fname)
        print(f"  {r['name']:<16} {r['category']:<8} {r['ic']:>8.4f} {r['t_stat']:>8.2f} {sig:>6} {r['n']:>6}")
    
    print(f"\n  显著因子 ({len(sig_factors)}): {', '.join(sig_factors)}")
    
    # 2. Stratified Backtest for top 4 factors
    print(f"\n  --- 分层回测 (Top 4 因子) ---")
    top_factors = [f for f, _ in sorted_ic[:4]]
    
    for fname in top_factors:
        result = stratified_backtest(fname, stock_universe[:15])
        if 'error' not in result:
            groups_str = ' | '.join([f"Q{g['group']}: {g['avg_return']:+.1f}%" for g in result['groups']])
            mono = '✅ 单调' if result['monotonic'] else '❌ 非单调'
            alpha = '🔴 Alpha!' if result['alpha_signal'] else ''
            print(f"  {result['factor_name']:<16} {groups_str}  {mono} {alpha}")
    
    # 3. Correlation Matrix
    print(f"\n  --- 因子相关性 ---")
    corr_result = compute_factor_correlation(stock_universe[:12])
    if 'error' not in corr_result:
        high_pairs = corr_result.get('high_correlation_pairs', [])
        if high_pairs:
            for pair in high_pairs:
                print(f"  ⚠️ {pair['pair']}: r={pair['correlation']:.2f} (高相关)")
        else:
            print(f"  ✅ 无高相关因子对 (|r| > 0.7)")
    
    print(f"\n{'='*60}\n")
    
    return {
        'ic_analysis': {f: r for f, r in sorted_ic},
        'significant_factors': sig_factors,
        'correlation': corr_result,
    }


# CLI
if __name__ == '__main__':
    import sys
    universe = sys.argv[1:] if len(sys.argv) > 1 else None
    full_factor_analysis(universe)
