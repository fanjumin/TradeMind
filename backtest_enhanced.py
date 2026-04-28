"""
TradeMind Enhanced Backtesting Engine
=======================================
Extends the core backtest.py with:
1. New strategy types: Momentum, Mean Reversion, Bollinger Bands, MACD, Volume Breakout
2. Parameter optimization (grid search)
3. Buy-and-hold benchmark
4. Enhanced risk metrics: Sortino, Calmar, max consecutive losses
5. Strategy comparison mode
"""

import pandas as pd
import numpy as np
from datetime import datetime
import itertools
from backtest import (
    BacktestResult, CostModel, BacktestEngine,
    strategy_ma_cross, strategy_rsi, strategy_kdj, strategy_macd as strategy_macd_bt,
    run_backtest as core_run_backtest
)

# Wrapper functions (backtest uses name without underscore; enhanced uses with underscore)
def _strategy_ma_cross(df, **kwargs):
    return strategy_ma_cross(df, **kwargs)

def _strategy_rsi(df, **kwargs):
    return strategy_rsi(df, **kwargs)

def _strategy_kdj(df, **kwargs):
    return strategy_kdj(df, **kwargs)

def _strategy_ma_rsi_combined(df, **kwargs):
    """MA+RSI combined strategy - enhanced version."""
    signals = pd.Series(0, index=df.index)
    ma_signals = strategy_ma_cross(df, short=kwargs.get('short_period', 5),
                                    long=kwargs.get('long_period', 20))
    rsi_signals = strategy_rsi(df, period=kwargs.get('rsi_period', 14),
                                oversold=kwargs.get('oversold', 30),
                                overbought=kwargs.get('overbought', 70))
    for i in range(len(df)):
        if ma_signals.iloc[i] == 1 and rsi_signals.iloc[i] >= 0:  # MA buy + RSI not overbought
            signals.iloc[i] = 1
        elif ma_signals.iloc[i] == -1 or rsi_signals.iloc[i] == -1:
            signals.iloc[i] = -1
    return signals

def _simulate_trades(df, signals, initial_capital, symbol, strategy_name):
    """Simulate trades from signals, returning BacktestResult."""
    result = BacktestResult(
        strategy_name=strategy_name,
        symbol=symbol,
        initial_capital=initial_capital,
        final_capital=initial_capital,
    )
    cash = initial_capital
    shares = 0
    trades = []
    entry_price = 0
    
    # Convert signals to list if needed
    if hasattr(signals, 'iloc'):
        signal_list = [signals.iloc[i] for i in range(len(signals))]
    elif hasattr(signals, '__iter__'):
        signal_list = list(signals)
    else:
        signal_list = [0] * len(df)
    
    for i in range(min(len(df), len(signal_list))):
        sig = signal_list[i]
        price = float(df['close'].iloc[i])
        date = str(df.index[i])[:10] if hasattr(df.index[i], 'strftime') else str(df.index[i])
        
        if sig == 1 and shares == 0:
            # Buy
            shares = int(cash * 0.95 / price / 100) * 100
            if shares >= 100:
                cost = shares * price
                commission = max(5, cost * 0.0003)
                cash -= (cost + commission)
                entry_price = price
                trades.append({'type': 'BUY', 'date': date, 'price': price, 
                              'shares': shares, 'cost': cost, 'commission': commission})
        elif sig == -1 and shares > 0:
            # Sell
            proceeds = shares * price
            commission = max(5, proceeds * 0.0003)
            stamp_tax = proceeds * 0.0005
            cash += (proceeds - commission - stamp_tax)
            pnl = shares * (price - entry_price) - commission - stamp_tax
            trades.append({'type': 'SELL', 'date': date, 'price': price,
                          'shares': shares, 'proceeds': proceeds, 'pnl': pnl,
                          'commission': commission, 'stamp_tax': stamp_tax})
            shares = 0
            entry_price = 0
    
    # Close any open position at last price
    if shares > 0:
        last_price = df['close'].iloc[-1]
        proceeds = shares * last_price
        cash += proceeds
        trades.append({'type': 'SELL (close)', 'date': str(df.index[-1])[:10],
                      'price': last_price, 'shares': shares, 'pnl': shares * (last_price - entry_price)})
    
    result.final_capital = cash
    result.total_return = (cash - initial_capital) / initial_capital
    
    # Calculate metrics
    sell_trades = [t for t in trades if 'SELL' in t['type']]
    if sell_trades:
        pnls = [t.get('pnl', 0) for t in sell_trades]
        result.total_trades = len(sell_trades)
        result.winning_trades = sum(1 for p in pnls if p > 0)
        result.losing_trades = sum(1 for p in pnls if p <= 0)
        result.win_rate = result.winning_trades / max(result.total_trades, 1)
        result.avg_win = np.mean([p for p in pnls if p > 0]) if result.winning_trades > 0 else 0
        result.avg_loss = abs(np.mean([p for p in pnls if p <= 0])) if result.losing_trades > 0 else 0
        if result.losing_trades == 0:
            result.profit_factor = 999.0  # No losses = effectively infinite
        else:
            result.profit_factor = (result.avg_win * result.winning_trades) / max(result.avg_loss * result.losing_trades, 0.01)
        
        # Sharpe ratio (simplified)
        if len(pnls) > 1:
            returns_pct = [p / initial_capital for p in pnls]
            result.sharpe_ratio = np.mean(returns_pct) / max(np.std(returns_pct), 0.0001) * np.sqrt(len(pnls))
        
        # Annualized return
        days = len(df)
        if days > 0 and result.total_return > -1:
            result.annualized_return = (1 + result.total_return) ** (252 / max(days, 1)) - 1
        
        # Max drawdown: based on cumulative P&L relative to peak
        cumulative = np.cumsum(pnls)
        peak = np.maximum.accumulate(cumulative)
        # Drawdown as percentage of peak portfolio value
        peak_value = initial_capital + peak
        drawdowns = np.where(peak_value > 0, (peak - cumulative) / peak_value, 0)
        result.max_drawdown = float(drawdowns.max()) if len(drawdowns) > 0 else 0
    
    result.trades = trades
    result.start_date = str(df.index[0])[:10] if hasattr(df.index[0], 'strftime') else str(df.index[0])
    result.end_date = str(df.index[-1])[:10] if hasattr(df.index[-1], 'strftime') else str(df.index[-1])
    
    return result


# ============================================================
# NEW STRATEGY TYPES
# ============================================================

def _strategy_momentum(df, lookback=20, threshold=0.05, **kwargs):
    """
    Momentum strategy: Buy when price return over lookback > threshold,
    sell when return turns negative.
    """
    signals = []
    returns = df['close'].pct_change(lookback)

    position = 0
    for i in range(len(df)):
        ret = returns.iloc[i]
        signal = 0

        if pd.isna(ret):
            signals.append(0)
            continue

        if position == 0 and ret > threshold:
            signal = 1
            position = 1
        elif position == 1 and ret < 0:
            signal = -1
            position = 0

        signals.append(signal)

    # Force close at end
    if position == 1 and signals:
        signals[-1] = -1

    return signals


def _strategy_mean_reversion(df, window=20, z_threshold=2.0, **kwargs):
    """
    Mean reversion: Buy when price falls z_threshold std below SMA,
    sell when price returns to SMA or above.
    """
    signals = []
    sma = df['close'].rolling(window=window).mean()
    std = df['close'].rolling(window=window).std()
    z_score = (df['close'] - sma) / std

    position = 0
    for i in range(len(df)):
        z = z_score.iloc[i]
        signal = 0

        if pd.isna(z):
            signals.append(0)
            continue

        if position == 0 and z < -z_threshold:
            signal = 1
            position = 1
        elif position == 1 and z > 0:
            signal = -1
            position = 0

        signals.append(signal)

    if position == 1 and signals:
        signals[-1] = -1

    return signals


def _strategy_bollinger(df, period=20, std_dev=2.0, **kwargs):
    """
    Bollinger Bands: Buy when price touches lower band,
    sell when price touches upper band.
    """
    signals = []
    sma = df['close'].rolling(window=period).mean()
    std = df['close'].rolling(window=period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std

    position = 0
    for i in range(len(df)):
        signal = 0
        price = df['close'].iloc[i]

        if pd.isna(upper.iloc[i]):
            signals.append(0)
            continue

        if position == 0 and price <= lower.iloc[i]:
            signal = 1
            position = 1
        elif position == 1 and price >= upper.iloc[i]:
            signal = -1
            position = 0

        signals.append(signal)

    if position == 1 and signals:
        signals[-1] = -1

    return signals


def _strategy_macd(df, fast=12, slow=26, signal_period=9, **kwargs):
    """
    MACD strategy: Buy when MACD crosses above signal line,
    sell when MACD crosses below signal line.
    """
    signals = []
    ema_fast = df['close'].ewm(span=fast).mean()
    ema_slow = df['close'].ewm(span=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period).mean()

    prev_macd = None
    prev_signal = None

    for i in range(len(df)):
        curr_macd = macd_line.iloc[i]
        curr_sig = signal_line.iloc[i]
        signal = 0

        if pd.isna(curr_macd) or pd.isna(curr_sig):
            signals.append(0)
            prev_macd = curr_macd
            prev_signal = curr_sig
            continue

        if prev_macd is not None and prev_signal is not None:
            if prev_macd <= prev_signal and curr_macd > curr_sig:
                signal = 1
            elif prev_macd >= prev_signal and curr_macd < curr_sig:
                signal = -1

        signals.append(signal)
        prev_macd = curr_macd
        prev_signal = curr_sig

    return signals


def _strategy_volume_breakout(df, volume_period=20, price_period=20, **kwargs):
    """
    Volume breakout: Buy when price breaks N-day high AND volume > avg * 1.5,
    sell when price drops below M-day low.
    """
    signals = []
    high_rolling = df['high'].rolling(window=price_period).max()
    low_rolling = df['low'].rolling(window=price_period).min()
    avg_volume = df['volume'].rolling(window=volume_period).mean()

    position = 0
    for i in range(len(df)):
        signal = 0
        price = df['close'].iloc[i]
        vol = df['volume'].iloc[i]
        avg_vol = avg_volume.iloc[i]

        if pd.isna(high_rolling.iloc[i]) or pd.isna(avg_vol):
            signals.append(0)
            continue

        if position == 0 and price >= high_rolling.iloc[i] and vol > avg_vol * 1.5:
            signal = 1
            position = 1
        elif position == 1 and price <= low_rolling.iloc[i]:
            signal = -1
            position = 0

        signals.append(signal)

    if position == 1 and signals:
        signals[-1] = -1

    return signals


# ============================================================
# STRATEGY REGISTRY
# ============================================================

STRATEGY_REGISTRY = {
    # Core strategies
    'ma_cross': {
        'fn': _strategy_ma_cross, 'name': 'MA金叉死叉',
        'category': 'trend', 'risk_level': 'low', 'timeframe': 'swing',
        'description': '经典双均线策略。短期均线上穿长期均线买入，下穿卖出。简单有效，适合趋势市。',
        'tags': ['均线', '金叉', '趋势', '经典'],
        'default_params': {'short_period': 5, 'long_period': 20},
    },
    'rsi': {
        'fn': _strategy_rsi, 'name': 'RSI超买超卖',
        'category': 'mean_reversion', 'risk_level': 'medium', 'timeframe': 'swing',
        'description': 'RSI低于超卖线买入，高于超买线卖出。震荡市中表现优异，趋势市中需谨慎。',
        'tags': ['RSI', '超买超卖', '震荡', '反转'],
        'default_params': {'rsi_period': 14, 'oversold': 30, 'overbought': 70},
    },
    'kdj': {
        'fn': _strategy_kdj, 'name': 'KDJ指标',
        'category': 'mean_reversion', 'risk_level': 'medium', 'timeframe': 'swing',
        'description': '随机指标策略。K线上穿D线且处于低位时买入，K线下穿D线且处于高位时卖出。',
        'tags': ['KDJ', '随机指标', '超买超卖'],
        'default_params': {},
    },
    'ma_rsi_combined': {
        'fn': _strategy_ma_rsi_combined, 'name': 'MA+RSI组合',
        'category': 'combined', 'risk_level': 'medium', 'timeframe': 'swing',
        'description': '均线趋势+RSI超卖确认双重过滤。仅在趋势正确且RSI处于合适区域时交易，降低假信号。',
        'tags': ['组合', 'MA', 'RSI', '双重过滤'],
        'default_params': {},
    },
    # New strategies
    'momentum': {
        'fn': _strategy_momentum, 'name': '动量突破',
        'category': 'momentum', 'risk_level': 'high', 'timeframe': 'swing',
        'description': '价格突破N日最高点时买入，跌破N日最低点时卖出。追涨杀跌，趋势强市表现优异。',
        'tags': ['动量', '突破', '追涨', '趋势'],
        'default_params': {'lookback': 20, 'threshold': 0.05},
    },
    'mean_reversion': {
        'fn': _strategy_mean_reversion, 'name': '均值回归',
        'category': 'mean_reversion', 'risk_level': 'medium', 'timeframe': 'day',
        'description': '价格偏离均线超过N个标准差时反向操作。假设价格会回归均值，震荡市效果最好。',
        'tags': ['均值回归', '布林带', '震荡', '反转'],
        'default_params': {'window': 20, 'z_threshold': 2.0},
    },
    'bollinger': {
        'fn': _strategy_bollinger, 'name': '布林带',
        'category': 'mean_reversion', 'risk_level': 'medium', 'timeframe': 'swing',
        'description': '价格触及下轨买入，回归中轨卖出。利用布林带的统计特性捕捉超跌反弹机会。',
        'tags': ['布林带', 'Bollinger', '超跌反弹'],
        'default_params': {'period': 20, 'std_dev': 2.0},
    },
    'macd': {
        'fn': _strategy_macd, 'name': 'MACD',
        'category': 'trend', 'risk_level': 'medium', 'timeframe': 'swing',
        'description': '最经典的趋势跟踪策略。MACD金叉买入，死叉卖出。配合零轴判断多空方向更佳。',
        'tags': ['MACD', '金叉', '趋势', '经典'],
        'default_params': {'fast': 12, 'slow': 26, 'signal_period': 9},
    },
    'volume_breakout': {
        'fn': _strategy_volume_breakout, 'name': '放量突破',
        'category': 'volume', 'risk_level': 'high', 'timeframe': 'day',
        'description': '成交量放大配合价格突破时买入，量缩时卖出。量价配合是A股最有效的短线策略之一。',
        'tags': ['量价', '放量', '突破', '短线'],
        'default_params': {'volume_period': 20, 'price_period': 20},
    },
}


def run_enhanced_backtest(df, strategy_name, symbol="", initial_capital=1000000, **kwargs):
    """
    Run an enhanced backtest with all strategy types.
    Returns BacktestResult.
    """
    if df.empty or 'close' not in df.columns:
        return None

    if strategy_name not in STRATEGY_REGISTRY:
        return None

    strategy_info = STRATEGY_REGISTRY[strategy_name]
    strategy_fn = strategy_info['fn']

    # Merge default params with user params
    params = dict(strategy_info['default_params'])
    params.update(kwargs)

    signals = strategy_fn(df, **params)
    result = _simulate_trades(df, signals, initial_capital, symbol, strategy_info['name'])

    # Add enhanced metrics
    result = _add_enhanced_metrics(result, df)

    return result


def _add_enhanced_metrics(result, df):
    """Add Sortino ratio, Calmar ratio, and consecutive loss metrics."""
    # We need to re-simulate to get portfolio values
    # Extract from trades
    if not result.trades:
        result.sortino_ratio = 0
        result.calmar_ratio = 0
        result.max_consecutive_losses = 0
        return result

    # Rebuild portfolio values from trades
    cash = result.initial_capital
    shares = 0
    has_position = False
    portfolio_values = []

    signals = []
    for t in result.trades:
        # We don't have signals directly, skip for now
        pass

    # Calculate from trade P&Ls
    sell_trades = [t for t in result.trades if t['type'] == 'SELL']
    if sell_trades:
        pnls = [t.get('pnl', 0) for t in sell_trades]

        # Sortino ratio (using downside deviation)
        downside_returns = [p for p in pnls if p < 0]
        if downside_returns:
            downside_std = np.std(downside_returns)
            if downside_std > 0:
                avg_return = np.mean(pnls)
                result.sortino_ratio = round(avg_return / downside_std * np.sqrt(len(pnls)), 2)
            else:
                result.sortino_ratio = 999.0
        else:
            result.sortino_ratio = 999.0

        # Calmar ratio (annualized return / max drawdown)
        if result.max_drawdown > 0:
            result.calmar_ratio = round(result.annualized_return / result.max_drawdown, 3)
        else:
            result.calmar_ratio = 999.0

        # Max consecutive losses
        max_cons = 0
        curr_cons = 0
        for pnl in pnls:
            if pnl <= 0:
                curr_cons += 1
                max_cons = max(max_cons, curr_cons)
            else:
                curr_cons = 0
        result.max_consecutive_losses = max_cons
    else:
        result.sortino_ratio = 0
        result.calmar_ratio = 0
        result.max_consecutive_losses = 0

    return result


# ============================================================
# PARAMETER OPTIMIZATION (GRID SEARCH)
# ============================================================

def optimize_strategy(df, strategy_name, param_grid, symbol="", initial_capital=1000000, metric="total_return"):
    """
    Grid search over parameter space to find optimal parameters.

    Parameters:
        df: OHLCV DataFrame
        strategy_name: Strategy to optimize
        param_grid: Dict of {param_name: [value1, value2, ...]}
        metric: Metric to optimize ('total_return', 'sharpe_ratio', 'win_rate', 'profit_factor')

    Returns:
        {
            'best_params': {...},
            'best_metric': float,
            'best_result': BacktestResult,
            'all_results': [{'params': ..., metric: ..., ...}, ...]
        }
    """
    if strategy_name not in STRATEGY_REGISTRY:
        return {'error': f'Unknown strategy: {strategy_name}'}

    strategy_info = STRATEGY_REGISTRY[strategy_name]

    # Generate all parameter combinations
    param_names = list(param_grid.keys())
    param_values = list(param_grid.values())
    combinations = list(itertools.product(*param_values))

    results = []
    for combo in combinations:
        params = dict(zip(param_names, combo))
        result = run_enhanced_backtest(df, strategy_name, symbol, initial_capital, **params)
        if result and result.total_trades > 0:
            metric_value = getattr(result, metric, result.total_return)
            results.append({
                'params': params,
                'metric': round(metric_value, 4),
                'total_return': result.total_return,
                'sharpe_ratio': result.sharpe_ratio,
                'win_rate': result.win_rate,
                'max_drawdown': result.max_drawdown,
                'total_trades': result.total_trades,
                'profit_factor': result.profit_factor,
            })

    if not results:
        return {'error': 'No valid results from optimization'}

    # Sort by metric (higher is better)
    results.sort(key=lambda x: x['metric'], reverse=True)

    best = results[0]
    best_params = best['params']
    best_result = run_enhanced_backtest(df, strategy_name, symbol, initial_capital, **best_params)

    return {
        'strategy': strategy_info['name'],
        'best_params': best_params,
        'best_metric': best['metric'],
        'metric_name': metric,
        'best_result': {
            'total_return': best_result.total_return,
            'sharpe_ratio': best_result.sharpe_ratio,
            'win_rate': best_result.win_rate,
            'max_drawdown': best_result.max_drawdown,
            'total_trades': best_result.total_trades,
            'sortino_ratio': getattr(best_result, 'sortino_ratio', 0),
            'calmar_ratio': getattr(best_result, 'calmar_ratio', 0),
        },
        'all_results': results[:50],  # Top 50
        'total_combinations': len(combinations),
    }


# ============================================================
# BENCHMARK (BUY AND HOLD)
# ============================================================

def benchmark_buy_hold(df, initial_capital=1000000):
    """
    Calculate buy-and-hold benchmark metrics.
    """
    if df.empty or len(df) < 2:
        return None

    start_price = df['close'].iloc[0]
    end_price = df['close'].iloc[-1]
    total_return = (end_price - start_price) / start_price * 100

    days = (df.index[-1] - df.index[0]).days if len(df) > 1 else 1
    years = days / 365.25
    annualized = ((end_price / start_price) ** (1 / years) - 1) * 100 if years > 0 else 0

    # Max drawdown
    prices = df['close'].values
    peak = prices[0]
    max_dd = 0
    for p in prices:
        if p > peak:
            peak = p
        dd = (peak - p) / peak
        if dd > max_dd:
            max_dd = dd

    # Volatility
    returns = df['close'].pct_change().dropna()
    volatility = returns.std() * np.sqrt(252) * 100

    return {
        'strategy': '买入持有',
        'total_return': round(total_return, 2),
        'annualized_return': round(annualized, 2),
        'max_drawdown': round(max_dd * 100, 2),
        'volatility': round(volatility, 2),
        'start_price': round(start_price, 2),
        'end_price': round(end_price, 2),
    }


# ============================================================
# STRATEGY COMPARISON
# ============================================================

def compare_strategies(df, strategy_names=None, symbol="", initial_capital=1000000):
    """
    Run multiple strategies and compare results.
    """
    if strategy_names is None:
        strategy_names = list(STRATEGY_REGISTRY.keys())

    results = {}
    for name in strategy_names:
        if name in STRATEGY_REGISTRY:
            result = run_enhanced_backtest(df, name, symbol, initial_capital)
            if result:
                results[name] = {
                    'name': STRATEGY_REGISTRY[name]['name'],
                    'total_return': result.total_return,
                    'sharpe_ratio': result.sharpe_ratio,
                    'sortino_ratio': getattr(result, 'sortino_ratio', 0),
                    'calmar_ratio': getattr(result, 'calmar_ratio', 0),
                    'win_rate': result.win_rate,
                    'max_drawdown': result.max_drawdown,
                    'total_trades': result.total_trades,
                    'profit_factor': result.profit_factor,
                    'max_consecutive_losses': getattr(result, 'max_consecutive_losses', 0),
                }

    # Add benchmark
    benchmark = benchmark_buy_hold(df, initial_capital)
    if benchmark:
        results['buy_hold'] = benchmark

    # Sort by total return
    sorted_results = sorted(results.items(), key=lambda x: x[1].get('total_return', 0), reverse=True)

    return {
        'symbol': symbol,
        'period': f"{df.index[0]} to {df.index[-1]}",
        'strategies': dict(sorted_results),
        'best': sorted_results[0][0] if sorted_results else None,
    }


# ============================================================
# EQUITY CURVE GENERATOR
# ============================================================

def get_equity_curve(df, strategy_name, initial_capital=1000000, **kwargs):
    """
    Generate equity curve data for charting.
    Returns list of {date, capital, return_pct} dicts.
    """
    if strategy_name not in STRATEGY_REGISTRY:
        return []

    strategy_info = STRATEGY_REGISTRY[strategy_name]
    strategy_fn = strategy_info['fn']
    params = dict(strategy_info['default_params'])
    params.update(kwargs)

    signals = strategy_fn(df, **params)

    # Simulate
    cash = initial_capital
    shares = 0
    has_position = False
    curve = []

    for i in range(len(df)):
        price = df['close'].iloc[i]
        signal = signals[i]

        if signal == 1 and not has_position and cash > 0:
            max_shares = int(cash * 0.95 / price)
            buy_shares = (max_shares // 100) * 100
            if buy_shares >= 100:
                cash -= buy_shares * price
                shares = buy_shares
                has_position = True
        elif signal == -1 and has_position:
            cash += shares * price
            shares = 0
            has_position = False

        portfolio_value = cash + shares * price
        date_str = str(df.index[i].date()) if hasattr(df.index[i], 'date') else str(df.index[i])
        curve.append({
            'date': date_str,
            'capital': round(portfolio_value, 2),
            'return_pct': round((portfolio_value / initial_capital - 1) * 100, 2),
        })

    return curve


if __name__ == "__main__":
    import sys
    sys.path.insert(0, '.')
    from data.price import get_price_data

    print("TradeMind Enhanced Backtesting Engine")
    print()

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python backtest_enhanced.py <symbol>              - Run all strategies")
        print("  python backtest_enhanced.py <symbol> optimize <strat>")
        print("  python backtest_enhanced.py <symbol> compare")
        sys.exit(0)

    symbol = sys.argv[1]
    df = get_price_data(symbol, datalen=300)

    if df.empty:
        print(f"No data for {symbol}")
        sys.exit(1)

    if len(sys.argv) > 2:
        mode = sys.argv[2]

        if mode == "optimize":
            strat = sys.argv[3] if len(sys.argv) > 3 else "ma_cross"
            # Define param grid based on strategy
            param_grids = {
                'ma_cross': {'short_period': [3, 5, 10], 'long_period': [10, 20, 30, 60]},
                'rsi': {'rsi_period': [7, 14, 21], 'oversold': [20, 30], 'overbought': [70, 80]},
                'macd': {'fast': [8, 12], 'slow': [20, 26, 30], 'signal_period': [7, 9]},
                'bollinger': {'period': [15, 20, 25], 'std_dev': [1.5, 2.0, 2.5]},
                'momentum': {'lookback': [10, 20, 30], 'threshold': [0.02, 0.05, 0.08]},
                'mean_reversion': {'window': [15, 20, 30], 'z_threshold': [1.5, 2.0, 2.5]},
                'volume_breakout': {'volume_period': [10, 20], 'price_period': [10, 20]},
            }
            grid = param_grids.get(strat, {'short_period': [5, 10], 'long_period': [20, 30]})

            result = optimize_strategy(df, strat, grid, symbol)
            if 'error' in result:
                print(result['error'])
            else:
                print(f"=== Optimization: {result['strategy']} ===")
                print(f"Best params: {result['best_params']}")
                print(f"Best {result['metric_name']}: {result['best_metric']}")
                print()
                print(f"{'Params':<50} {'Return%':>8} {'Sharpe':>8} {'Win%':>6} {'DD%':>6} {'Trades':>6}")
                print("-" * 90)
                for r in result['all_results'][:20]:
                    print(f"{str(r['params']):<50} {r['total_return']:>8.2f} {r['sharpe_ratio']:>8.2f} {r['win_rate']:>6.1f} {r['max_drawdown']:>6.2f} {r['total_trades']:>6}")

        elif mode == "compare":
            result = compare_strategies(df, symbol=symbol)
            print(f"=== Strategy Comparison: {symbol} ({result['period']}) ===")
            print()
            print(f"{'Strategy':<20} {'Return%':>8} {'Sharpe':>8} {'Sortino':>8} {'Calmar':>8} {'Win%':>6} {'DD%':>6} {'Trades':>6}")
            print("-" * 90)
            for name, r in result['strategies'].items():
                print(f"{r.get('strategy', r.get('name', name)):<20} {r['total_return']:>8.2f} {r.get('sharpe_ratio', 0):>8.2f} {r.get('sortino_ratio', 0):>8.2f} {r.get('calmar_ratio', 0):>8.3f} {r.get('win_rate', 0):>6.1f} {r.get('max_drawdown', 0):>6.2f} {r.get('total_trades', 0):>6}")

    else:
        # Run all strategies
        result = compare_strategies(df, symbol=symbol)
        print(f"=== All Strategies: {symbol} ({result['period']}) ===")
        print()
        print(f"{'Strategy':<20} {'Return%':>8} {'Sharpe':>8} {'Sortino':>8} {'Calmar':>8} {'Win%':>6} {'DD%':>6} {'Trades':>6}")
        print("-" * 90)
        for name, r in result['strategies'].items():
            print(f"{r.get('strategy', r.get('name', name)):<20} {r['total_return']:>8.2f} {r.get('sharpe_ratio', 0):>8.2f} {r.get('sortino_ratio', 0):>8.2f} {r.get('calmar_ratio', 0):>8.3f} {r.get('win_rate', 0):>6.1f} {r.get('max_drawdown', 0):>6.2f} {r.get('total_trades', 0):>6}")
