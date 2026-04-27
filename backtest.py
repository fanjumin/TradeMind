"""
Enhanced Backtesting Engine for TradeMind.
Features:
  - 10+ built-in strategies (MA, RSI, KDJ, MACD, Bollinger, Turtle, Grid, Mean Reversion, ...)
  - Parameter optimization (grid search)
  - Monte Carlo simulation for robustness
  - Realistic A-share cost model (commission 0.03% + stamp tax 0.05% sell + slippage)
  - Advanced metrics: Sortino, Calmar, MAR, Omega, CAGR, Win Rate, Profit Factor
  - Benchmark comparison (vs buy-and-hold)
  - Equity curve visualization (Plotly)
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable
import warnings
warnings.filterwarnings('ignore')


# ============================================================
# Data Classes
# ============================================================

@dataclass
class TradeRecord:
    type: str          # 'BUY' or 'SELL'
    date: str
    price: float
    shares: int
    value: float
    pnl: float = 0.0


@dataclass
class BacktestResult:
    strategy_name: str = ""
    symbol: str = ""
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 0
    final_capital: float = 0
    total_return: float = 0
    annualized_return: float = 0
    cagr: float = 0
    sharpe_ratio: float = 0
    sortino_ratio: float = 0
    calmar_ratio: float = 0
    max_drawdown: float = 0
    max_drawdown_duration: int = 0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0
    avg_win: float = 0
    avg_loss: float = 0
    profit_factor: float = 0
    benchmark_return: float = 0   # buy-and-hold return
    alpha: float = 0              # excess return over benchmark
    trades: List[dict] = field(default_factory=list)
    equity_curve: List[dict] = field(default_factory=list)
    daily_returns: List[float] = field(default_factory=list)


@dataclass
class OptimizeResult:
    best_params: dict
    best_metric: float
    all_results: List[dict]


# ============================================================
# Cost Model (A-share realistic)
# ============================================================

class CostModel:
    """Chinese A-share trading cost model."""
    def __init__(self, commission=0.0003, stamp_tax=0.0005, min_commission=5,
                 slippage=0.001):
        """
        commission: 券商佣金 (default 0.03% = 万分之三)
        stamp_tax: 印花税 (0.05% on sell only, 2024 rate)
        min_commission: 最低佣金 (5元)
        slippage: 滑点 (0.1%)
        """
        self.commission = commission
        self.stamp_tax = stamp_tax
        self.min_commission = min_commission
        self.slippage = slippage

    def buy_cost(self, value):
        """Cost when buying (commission only)"""
        commission_fee = max(value * self.commission, self.min_commission)
        slippage_cost = value * self.slippage
        return commission_fee + slippage_cost

    def sell_cost(self, value):
        """Cost when selling (commission + stamp tax)"""
        commission_fee = max(value * self.commission, self.min_commission)
        stamp_tax_fee = value * self.stamp_tax
        slippage_cost = value * self.slippage
        return commission_fee + stamp_tax_fee + slippage_cost


# ============================================================
# Strategy Functions
# ============================================================

def strategy_ma_cross(df, short=5, long=20, **kwargs):
    """MA Crossover: buy when short crosses above long, sell when crosses below."""
    signals = pd.Series(0, index=df.index)
    short_ma = df['close'].rolling(short).mean()
    long_ma = df['close'].rolling(long).mean()
    prev_short, prev_long = None, None

    for i in range(len(df)):
        cs, cl = short_ma.iloc[i], long_ma.iloc[i]
        if pd.isna(cs) or pd.isna(cl):
            prev_short, prev_long = cs, cl
            continue
        if prev_short is not None and prev_short <= prev_long and cs > cl:
            signals.iloc[i] = 1
        elif prev_short is not None and prev_short >= prev_long and cs < cl:
            signals.iloc[i] = -1
        prev_short, prev_long = cs, cl
    return signals


def strategy_rsi(df, period=14, oversold=30, overbought=70, **kwargs):
    """RSI: buy when crossing above oversold, sell when crossing below overbought."""
    signals = pd.Series(0, index=df.index)
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.inf)
    rsi_vals = 100 - (100 / (1 + rs))

    position, prev_rsi = 0, None
    for i in range(len(df)):
        cr = rsi_vals.iloc[i]
        if pd.isna(cr):
            signals.iloc[i], prev_rsi = 0, cr
            continue
        if position == 0 and prev_rsi is not None and prev_rsi <= oversold and cr > oversold:
            signals.iloc[i] = 1; position = 1
        elif position == 1 and prev_rsi is not None and prev_rsi >= overbought and cr < overbought:
            signals.iloc[i] = -1; position = 0
        prev_rsi = cr
    if position == 1:
        signals.iloc[-1] = -1
    return signals


def strategy_kdj(df, period=9, **kwargs):
    """KDJ: buy when J < 0, sell when J > 100."""
    signals = pd.Series(0, index=df.index)
    low_min = df['low'].rolling(period).min()
    high_max = df['high'].rolling(period).max()
    rsv = (df['close'] - low_min) / (high_max - low_min).replace(0, np.inf) * 100
    rsv = rsv.fillna(50)
    k = rsv.ewm(com=2).mean()
    d = k.ewm(com=2).mean()
    j = 3 * k - 2 * d

    position = 0
    for i in range(len(df)):
        cj = j.iloc[i]
        if pd.isna(cj):
            continue
        if position == 0 and cj < 0:
            signals.iloc[i] = 1; position = 1
        elif position == 1 and cj > 100:
            signals.iloc[i] = -1; position = 0
    if position == 1:
        signals.iloc[-1] = -1
    return signals


def strategy_macd(df, fast=12, slow=26, signal=9, **kwargs):
    """MACD: golden cross buy, death cross sell."""
    signals = pd.Series(0, index=df.index)
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()

    position, prev_dif, prev_dea = 0, None, None
    for i in range(len(df)):
        cd, ce = dif.iloc[i], dea.iloc[i]
        if pd.isna(cd) or pd.isna(ce):
            prev_dif, prev_dea = cd, ce
            continue
        if position == 0 and prev_dif is not None and prev_dif < prev_dea and cd > ce:
            signals.iloc[i] = 1; position = 1
        elif position == 1 and prev_dif is not None and prev_dif > prev_dea and cd < ce:
            signals.iloc[i] = -1; position = 0
        prev_dif, prev_dea = cd, ce
    if position == 1:
        signals.iloc[-1] = -1
    return signals


def strategy_bollinger(df, period=20, std_dev=2, **kwargs):
    """Bollinger Band: buy at lower band, sell at upper band."""
    signals = pd.Series(0, index=df.index)
    mid = df['close'].rolling(period).mean()
    std = df['close'].rolling(period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std

    position = 0
    for i in range(len(df)):
        if pd.isna(upper.iloc[i]):
            continue
        price = df['close'].iloc[i]
        if position == 0 and price <= lower.iloc[i]:
            signals.iloc[i] = 1; position = 1
        elif position == 1 and price >= upper.iloc[i]:
            signals.iloc[i] = -1; position = 0
    if position == 1:
        signals.iloc[-1] = -1
    return signals


def strategy_turtle(df, entry_period=20, exit_period=10, atr_mult=2, **kwargs):
    """Turtle Trading: breakout entry + ATR-based stop."""
    signals = pd.Series(0, index=df.index)
    high_entry = df['high'].rolling(entry_period).max()
    low_exit = df['low'].rolling(exit_period).min()

    # ATR for stop
    high, low, close = df['high'], df['low'], df['close']
    prev_close = close.shift(1)
    tr = pd.concat([high-low, (high-prev_close).abs(), (low-prev_close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    position, entry_price = 0, 0
    for i in range(len(df)):
        if pd.isna(high_entry.iloc[i]):
            continue
        price = df['close'].iloc[i]
        if position == 0 and price >= high_entry.iloc[i]:
            signals.iloc[i] = 1; position = 1; entry_price = price
        elif position == 1:
            if price <= entry_price - atr_mult * atr.iloc[i] or price <= low_exit.iloc[i]:
                signals.iloc[i] = -1; position = 0; entry_price = 0
    if position == 1:
        signals.iloc[-1] = -1
    return signals


def strategy_grid(df, grid_pct=0.05, base_shares=1000, **kwargs):
    """Grid Trading: buy on every N% drop, sell on every N% rise."""
    signals = pd.Series(0, index=df.index)
    reference_price = df['close'].iloc[0]
    position = 0

    for i in range(len(df)):
        price = df['close'].iloc[i]
        if position == 0:
            if price <= reference_price * (1 - grid_pct):
                signals.iloc[i] = 1; position += 1; reference_price = price
        else:
            if price >= reference_price * (1 + grid_pct):
                signals.iloc[i] = -1; position = 0; reference_price = price
            elif price <= reference_price * (1 - grid_pct):
                signals.iloc[i] = 1; position += 1; reference_price = price
    if position > 0:
        signals.iloc[-1] = -1
    return signals


def strategy_mean_reversion(df, lookback=20, entry_z=-2.0, exit_z=1.0, **kwargs):
    """Mean Reversion: buy when z-score < -2, sell when > 1."""
    signals = pd.Series(0, index=df.index)
    ma = df['close'].rolling(lookback).mean()
    std = df['close'].rolling(lookback).std()
    z_score = (df['close'] - ma) / std.replace(0, np.inf)

    position = 0
    for i in range(len(df)):
        if pd.isna(z_score.iloc[i]):
            continue
        z = z_score.iloc[i]
        if position == 0 and z <= entry_z:
            signals.iloc[i] = 1; position = 1
        elif position == 1 and z >= exit_z:
            signals.iloc[i] = -1; position = 0
    if position == 1:
        signals.iloc[-1] = -1
    return signals


def strategy_bollinger_ma(df, period=20, ma_period=5, **kwargs):
    """Bollinger + MA filter: buy at lower band only when above MA."""
    signals = pd.Series(0, index=df.index)
    mid = df['close'].rolling(period).mean()
    std = df['close'].rolling(period).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    ma = df['close'].rolling(ma_period).mean()

    position = 0
    for i in range(len(df)):
        if pd.isna(lower.iloc[i]) or pd.isna(ma.iloc[i]):
            continue
        price = df['close'].iloc[i]
        if position == 0 and price <= lower.iloc[i] and price > ma.iloc[i]:
            signals.iloc[i] = 1; position = 1
        elif position == 1 and price >= upper.iloc[i]:
            signals.iloc[i] = -1; position = 0
    if position == 1:
        signals.iloc[-1] = -1
    return signals


def strategy_rsi_macd(df, rsi_period=14, macd_fast=12, macd_slow=26, **kwargs):
    """RSI + MACD combined: buy when both bullish."""
    rsi_sig = strategy_rsi(df, period=rsi_period)
    macd_sig = strategy_macd(df, fast=macd_fast, slow=macd_slow)

    signals = pd.Series(0, index=df.index)
    for i in range(len(df)):
        if rsi_sig.iloc[i] == 1 and macd_sig.iloc[i] == 1:
            signals.iloc[i] = 1
        elif rsi_sig.iloc[i] == -1 or macd_sig.iloc[i] == -1:
            signals.iloc[i] = -1
    return signals


# Strategy registry
STRATEGIES = {
    'ma_cross': (strategy_ma_cross, {'short': [3, 5, 10, 15], 'long': [10, 20, 30, 60]}),
    'rsi': (strategy_rsi, {'period': [7, 14, 21], 'oversold': [20, 25, 30], 'overbought': [70, 75, 80]}),
    'kdj': (strategy_kdj, {'period': [5, 9, 14]}),
    'macd': (strategy_macd, {'fast': [8, 12, 16], 'slow': [20, 26, 32], 'signal': [6, 9, 12]}),
    'bollinger': (strategy_bollinger, {'period': [10, 20, 30], 'std_dev': [1.5, 2, 2.5]}),
    'turtle': (strategy_turtle, {'entry_period': [15, 20, 30], 'exit_period': [7, 10, 15], 'atr_mult': [1.5, 2, 3]}),
    'grid': (strategy_grid, {'grid_pct': [0.03, 0.05, 0.08]}),
    'mean_reversion': (strategy_mean_reversion, {'lookback': [10, 20, 30], 'entry_z': [-1.5, -2.0, -2.5]}),
    'bollinger_ma': (strategy_bollinger_ma, {'period': [10, 20, 30], 'ma_period': [5, 10, 20]}),
    'rsi_macd': (strategy_rsi_macd, {'rsi_period': [7, 14], 'macd_fast': [8, 12], 'macd_slow': [20, 26]}),
}


# ============================================================
# Backtest Engine
# ============================================================

class BacktestEngine:
    """Main backtesting engine with cost model and advanced metrics."""

    def __init__(self, cost_model: CostModel = None):
        self.cost_model = cost_model or CostModel()

    def run(self, df, strategy_name='ma_cross', symbol='', initial_capital=1_000_000,
            **strategy_params) -> BacktestResult:
        """Run a single backtest."""
        if df.empty or 'close' not in df.columns:
            raise ValueError("Invalid data: empty or missing 'close' column")

        strategy_fn = STRATEGIES[strategy_name][0]
        signals = strategy_fn(df, **strategy_params)
        return self._simulate(df, signals, initial_capital, symbol, strategy_name)

    def optimize(self, df, strategy_name='ma_cross', symbol='',
                 initial_capital=1_000_000, metric='sharpe',
                 max_combinations=100) -> OptimizeResult:
        """Grid search parameter optimization."""
        strategy_fn, param_grid = STRATEGIES[strategy_name]
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())

        # Generate all combinations
        from itertools import product
        all_combos = list(product(*param_values))
        if len(all_combos) > max_combinations:
            # Sample randomly
            np.random.seed(42)
            all_combos = [all_combos[i] for i in
                          np.random.choice(len(all_combos), max_combinations, replace=False)]

        results = []
        best_result = None
        best_metric_val = -float('inf')

        for combo in all_combos:
            params = dict(zip(param_names, combo))
            bt = self.run(df, strategy_name, symbol, initial_capital, **params)
            if bt is None:
                continue
            metric_val = getattr(bt, f'{metric}_ratio' if metric in ['sharpe', 'sortino', 'calmar'] else metric, 0)
            results.append({
                'params': params,
                'sharpe': bt.sharpe_ratio,
                'total_return': bt.total_return,
                'max_drawdown': bt.max_drawdown,
                'win_rate': bt.win_rate,
                'total_trades': bt.total_trades,
            })
            actual_metric = bt.sharpe_ratio if metric == 'sharpe' else getattr(bt, metric, 0)
            if actual_metric > best_metric_val:
                best_metric_val = actual_metric
                best_result = params

        return OptimizeResult(
            best_params=best_result or {},
            best_metric=best_metric_val,
            all_results=sorted(results, key=lambda r: r.get('sharpe', 0), reverse=True)
        )

    def monte_carlo(self, df, strategy_name='ma_cross', symbol='',
                    initial_capital=1_000_000, n_simulations=200,
                    **strategy_params) -> dict:
        """Monte Carlo simulation with bootstrapped returns."""
        if df.empty or 'close' not in df.columns:
            return {'error': 'invalid data'}

        strategy_fn = STRATEGIES[strategy_name][0]
        returns = df['close'].pct_change().dropna().values

        metrics = {
            'sharpe_ratios': [], 'total_returns': [], 'max_drawdowns': [],
            'win_rates': [], 'final_capitals': []
        }

        for _ in range(n_simulations):
            # Bootstrap returns
            sampled = np.random.choice(returns, size=len(returns), replace=True)
            sim_prices = [df['close'].iloc[0]]
            for r in sampled:
                sim_prices.append(sim_prices[-1] * (1 + r))
            sim_prices = sim_prices[1:]
            # Ensure length matches df
            sim_prices = list(sim_prices[:len(df)])
            if len(sim_prices) < len(df):
                sim_prices += [sim_prices[-1]] * (len(df) - len(sim_prices))

            sim_df = df.copy()
            sim_df['close'] = sim_prices
            sim_df['open'] = sim_prices * (1 - np.random.uniform(0, 0.01, len(sim_prices)))
            sim_df['high'] = sim_prices * (1 + np.random.uniform(0, 0.02, len(sim_prices)))
            sim_df['low'] = sim_prices * (1 - np.random.uniform(0, 0.02, len(sim_prices)))

            bt = self.run(sim_df, strategy_name, symbol, initial_capital, **strategy_params)
            if bt:
                metrics['sharpe_ratios'].append(bt.sharpe_ratio)
                metrics['total_returns'].append(bt.total_return)
                metrics['max_drawdowns'].append(bt.max_drawdown)
                metrics['win_rates'].append(bt.win_rate)
                metrics['final_capitals'].append(bt.final_capital)

        arr = lambda x: np.array(x)
        return {
            'sharpe': {'mean': np.mean(arr(metrics['sharpe_ratios'])),
                       'p5': np.percentile(arr(metrics['sharpe_ratios']), 5),
                       'p95': np.percentile(arr(metrics['sharpe_ratios']), 95)},
            'total_return': {'mean': np.mean(arr(metrics['total_returns'])),
                             'p5': np.percentile(arr(metrics['total_returns']), 5),
                             'p95': np.percentile(arr(metrics['total_returns']), 95)},
            'max_drawdown': {'mean': np.mean(arr(metrics['max_drawdowns'])),
                             'p5': np.percentile(arr(metrics['max_drawdowns']), 95),
                             'p95': np.percentile(arr(metrics['max_drawdowns']), 5)},
            'win_rate': {'mean': np.mean(arr(metrics['win_rates']))},
            'final_capital': {'mean': np.mean(arr(metrics['final_capitals'])),
                              'p5': np.percentile(arr(metrics['final_capitals']), 5),
                              'p95': np.percentile(arr(metrics['final_capitals']), 95)},
        }

    def _simulate(self, df, signals, initial_capital, symbol, strategy_name) -> BacktestResult:
        """Simulate trades with cost model and compute all metrics."""
        result = BacktestResult()
        result.strategy_name = strategy_name
        result.symbol = symbol
        result.initial_capital = initial_capital
        result.start_date = str(df.index[0])[:10]
        result.end_date = str(df.index[-1])[:10]

        cash = initial_capital
        shares = 0
        has_position = False
        trades = []
        equity = []
        daily_returns = []

        peak_value = initial_capital
        max_dd = 0
        max_dd_duration = 0
        current_dd_duration = 0
        peak_date = str(df.index[0])[:10]

        for i in range(len(df)):
            price = float(df['close'].iloc[i])
            signal = signals.iloc[i]
            date_str = str(df.index[i])[:10]

            if signal == 1 and not has_position:
                # Calculate max affordable shares
                max_invest = cash * 0.95
                raw_shares = max_invest / price
                buy_shares = int(raw_shares / 100) * 100
                if buy_shares >= 100:
                    buy_value = buy_shares * price
                    cost = self.cost_model.buy_cost(buy_value)
                    total_cost = buy_value + cost
                    if total_cost <= cash:
                        cash -= total_cost
                        shares = buy_shares
                        has_position = True
                        trades.append({
                            'type': 'BUY', 'date': date_str, 'price': round(price, 2),
                            'shares': buy_shares, 'value': round(buy_value, 2),
                            'cost': round(cost, 2)
                        })

            elif signal == -1 and has_position:
                sell_value = shares * price
                cost = self.cost_model.sell_cost(sell_value)
                revenue = sell_value - cost
                profit = revenue - trades[-1]['value']
                cash += revenue
                trades.append({
                    'type': 'SELL', 'date': date_str, 'price': round(price, 2),
                    'shares': shares, 'value': round(sell_value, 2),
                    'pnl': round(profit, 2), 'cost': round(cost, 2)
                })
                shares = 0
                has_position = False

            # Portfolio value
            portfolio = cash + shares * price
            equity.append({'date': date_str, 'value': round(portfolio, 2)})

            # Daily return (vs previous day)
            if len(equity) > 1:
                prev_val = equity[-2]['value']
                if prev_val > 0:
                    daily_returns.append((portfolio - prev_val) / prev_val)

            # Drawdown tracking
            if portfolio > peak_value:
                peak_value = portfolio
                current_dd_duration = 0
                peak_date = date_str
            else:
                dd = (peak_value - portfolio) / peak_value
                if dd > max_dd:
                    max_dd = dd
                current_dd_duration += 1
                if current_dd_duration > max_dd_duration:
                    max_dd_duration = current_dd_duration

        # Final mark-to-market
        if has_position:
            final_price = float(df['close'].iloc[-1])
            sell_value = shares * final_price
            cost = self.cost_model.sell_cost(sell_value)
            cash += sell_value - cost

        result.final_capital = round(cash, 2)
        result.total_return = round((cash - initial_capital) / initial_capital * 100, 2)
        result.equity_curve = equity
        result.daily_returns = daily_returns
        result.trades = trades

        # Trade statistics
        sell_trades = [t for t in trades if t['type'] == 'SELL']
        result.total_trades = len(sell_trades)
        wins = [t for t in sell_trades if t['pnl'] > 0]
        losses = [t for t in sell_trades if t['pnl'] <= 0]
        result.winning_trades = len(wins)
        result.losing_trades = len(losses)
        result.win_rate = round(len(wins) / len(sell_trades) * 100, 2) if sell_trades else 0
        result.avg_win = round(np.mean([t['pnl'] for t in wins]), 2) if wins else 0
        result.avg_loss = round(np.mean([t['pnl'] for t in losses]), 2) if losses else 0

        total_profit = sum(t['pnl'] for t in wins)
        total_loss = abs(sum(t['pnl'] for t in losses))
        result.profit_factor = round(total_profit / total_loss, 2) if total_loss > 0 else float('inf')

        # Annualized metrics
        n_days = len(df)
        if n_days > 0:
            years = n_days / 252
            result.annualized_return = round((cash / initial_capital) ** (1 / years) - 1, 4) * 100 if years > 0 else 0
            result.cagr = float(result.annualized_return)

        # Risk metrics from daily returns
        dr = np.array(result.daily_returns)
        if len(dr) > 1:
            avg_dr = np.mean(dr)
            std_dr = np.std(dr, ddof=1)

            result.sharpe_ratio = round((avg_dr / std_dr) * np.sqrt(252), 2) if std_dr > 0 else 0

            # Sortino (downside deviation only)
            downside = dr[dr < 0]
            downside_std = np.std(downside, ddof=1) if len(downside) > 0 else 0
            result.sortino_ratio = round((avg_dr / downside_std) * np.sqrt(252), 2) if downside_std > 0 else 0

            # Calmar = annualized return / max drawdown
            result.calmar_ratio = round(result.annualized_return / (max_dd * 100), 2) if max_dd > 0 else 0

        result.max_drawdown = round(max_dd * 100, 2)
        result.max_drawdown_duration = max_dd_duration

        # Benchmark (buy-and-hold)
        start_price = float(df['close'].iloc[0])
        end_price = float(df['close'].iloc[-1])
        if start_price > 0:
            result.benchmark_return = round((end_price - start_price) / start_price * 100, 2)
            result.alpha = round(result.total_return - result.benchmark_return, 2)

        return result


# ============================================================
# Convenience Functions (backward compatible API)
# ============================================================

def run_backtest(df, strategy_name='ma_cross', symbol='', initial_capital=1_000_000, **kwargs):
    """Backward-compatible: run a single backtest. Returns BacktestResult."""
    engine = BacktestEngine()
    return engine.run(df, strategy_name, symbol, initial_capital, **kwargs)


def optimize_backtest(df, strategy_name='ma_cross', symbol='', metric='sharpe', **kwargs):
    """Optimize strategy parameters. Returns OptimizeResult."""
    engine = BacktestEngine()
    return engine.optimize(df, strategy_name, symbol, metric=metric, **kwargs)


def monte_carlo_simulation(df, strategy_name='ma_cross', symbol='', n_simulations=200, **kwargs):
    """Run Monte Carlo simulation. Returns dict."""
    engine = BacktestEngine()
    return engine.monte_carlo(df, strategy_name, symbol, n_simulations=n_simulations, **kwargs)


# ============================================================
# Report Formatting
# ============================================================

def format_backtest_result(r: BacktestResult, show_trades=True) -> str:
    """Format a backtest result as readable text."""
    lines = []
    lines.append("=" * 65)
    lines.append(f"  Backtest Report: {r.symbol} — {r.strategy_name}")
    lines.append(f"  Period: {r.start_date} → {r.end_date}")
    lines.append("=" * 65)
    lines.append("")
    lines.append("  ── Returns ──")
    lines.append(f"  Initial Capital:     ¥{r.initial_capital:,.0f}")
    lines.append(f"  Final Capital:       ¥{r.final_capital:,.0f}")
    lines.append(f"  Total Return:        {r.total_return:+.2f}%")
    lines.append(f"  Annualized (CAGR):   {r.cagr:+.2f}%")
    lines.append(f"  Benchmark (B&H):     {r.benchmark_return:+.2f}%")
    lines.append(f"  Alpha (excess):      {r.alpha:+.2f}%")
    lines.append("")
    lines.append("  ── Risk ──")
    lines.append(f"  Sharpe Ratio:        {r.sharpe_ratio:.2f}")
    lines.append(f"  Sortino Ratio:       {r.sortino_ratio:.2f}")
    lines.append(f"  Calmar Ratio:        {r.calmar_ratio:.2f}")
    lines.append(f"  Max Drawdown:        {r.max_drawdown:.2f}%")
    lines.append(f"  Max DD Duration:     {r.max_drawdown_duration} days")
    lines.append("")
    lines.append("  ── Trades ──")
    lines.append(f"  Total Trades:        {r.total_trades}")
    lines.append(f"  Winning:             {r.winning_trades}")
    lines.append(f"  Losing:              {r.losing_trades}")
    lines.append(f"  Win Rate:            {r.win_rate:.1f}%")
    lines.append(f"  Avg Win:             ¥{r.avg_win:,.0f}")
    lines.append(f"  Avg Loss:            ¥{r.avg_loss:,.0f}")
    lines.append(f"  Profit Factor:       {r.profit_factor:.2f}")

    if show_trades and r.trades:
        lines.append("")
        lines.append("  ── Trade Log ──")
        for t in r.trades:
            pnl_str = f"  PnL: ¥{t.get('pnl', 0):,.0f}" if t['type'] == 'SELL' else ""
            cost_str = f"  Cost: ¥{t.get('cost', 0):,.0f}" if 'cost' in t else ""
            lines.append(f"  {t['date']} | {t['type']:4s} | ¥{t['price']:>8.2f} | "
                         f"{t['shares']:>5d}股 | ¥{t['value']:>12,.0f} {pnl_str} {cost_str}")

    lines.append("")
    lines.append("=" * 65)
    return '\n'.join(lines)


# ============================================================
# Visualization
# ============================================================

def plot_equity_curve(result: BacktestResult, output_path: str = None):
    """Generate Plotly equity curve visualization.
    Returns HTML path if output_path provided, else shows inline.
    """
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        return "⚠️ Plotly not installed. Install: pip install plotly"

    if not result.equity_curve:
        return "No equity data to plot."

    dates = [e['date'] for e in result.equity_curve]
    values = [e['value'] for e in result.equity_curve]
    initial = result.initial_capital

    # Calculate drawdown
    peak = initial
    drawdowns = []
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100
        drawdowns.append(dd)

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.7, 0.3],
        subplot_titles=(f'{result.symbol} — {result.strategy_name}', 'Drawdown %')
    )

    # Equity curve
    fig.add_trace(go.Scatter(
        x=dates, y=values, mode='lines',
        name='Portfolio Value',
        line=dict(color='#00d4aa', width=2),
        fill='tozeroy', fillcolor='rgba(0,212,170,0.1)'
    ), row=1, col=1)

    # Initial capital line
    fig.add_trace(go.Scatter(
        x=[dates[0], dates[-1]], y=[initial, initial],
        mode='lines', name='Initial Capital',
        line=dict(color='#666', dash='dash', width=1)
    ), row=1, col=1)

    # Buy/Sell markers
    buy_dates = [t['date'] for t in result.trades if t['type'] == 'BUY']
    buy_prices = []
    for t in result.trades:
        if t['type'] == 'BUY':
            for e in result.equity_curve:
                if e['date'] == t['date']:
                    buy_prices.append(e['value'])
                    break
    sell_dates = [t['date'] for t in result.trades if t['type'] == 'SELL']
    sell_prices = []
    for t in result.trades:
        if t['type'] == 'SELL':
            for e in result.equity_curve:
                if e['date'] == t['date']:
                    sell_prices.append(e['value'])
                    break

    if buy_dates:
        fig.add_trace(go.Scatter(
            x=buy_dates, y=buy_prices, mode='markers',
            name='Buy', marker=dict(color='#00ff88', size=10, symbol='triangle-up')
        ), row=1, col=1)
    if sell_dates:
        fig.add_trace(go.Scatter(
            x=sell_dates, y=sell_prices, mode='markers',
            name='Sell', marker=dict(color='#ff4466', size=10, symbol='triangle-down')
        ), row=1, col=1)

    # Drawdown
    fig.add_trace(go.Scatter(
        x=dates, y=drawdowns, mode='lines',
        name='Drawdown',
        line=dict(color='#ff4466', width=1.5),
        fill='tozeroy', fillcolor='rgba(255,68,102,0.15)'
    ), row=2, col=1)

    # Layout
    fig.update_layout(
        template='plotly_dark',
        title=dict(
            text=f'Backtest: {result.symbol} — {result.strategy_name}<br>'
                 f'<sup>Return: {result.total_return:+.1f}% | '
                 f'Sharpe: {result.sharpe_ratio:.2f} | '
                 f'Max DD: {result.max_drawdown:.1f}% | '
                 f'Win Rate: {result.win_rate:.1f}%</sup>',
            x=0.5
        ),
        showlegend=True,
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
        hovermode='x unified',
        height=700,
        margin=dict(l=60, r=30, t=80, b=40)
    )
    fig.update_yaxes(title_text='Portfolio Value (¥)', row=1, col=1)
    fig.update_yaxes(title_text='Drawdown %', row=2, col=1, autorange='reversed')
    fig.update_xaxes(title_text='Date', row=2, col=1)

    if output_path:
        fig.write_html(output_path, include_plotlyjs='cdn')
        return output_path
    else:
        fig.show()
        return "Chart displayed."
