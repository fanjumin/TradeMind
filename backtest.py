"""
Backtesting engine for trading strategies.
Supports MA crossover, RSI, KDJ, and combined strategies.
Returns performance metrics: Sharpe ratio, max drawdown, win rate, etc.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


class BacktestResult:
    def __init__(self):
        self.strategy_name = ""
        self.symbol = ""
        self.start_date = ""
        self.end_date = ""
        self.initial_capital = 0
        self.final_capital = 0
        self.total_return = 0
        self.annualized_return = 0
        self.sharpe_ratio = 0
        self.max_drawdown = 0
        self.max_drawdown_duration = 0
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.win_rate = 0
        self.avg_win = 0
        self.avg_loss = 0
        self.profit_factor = 0
        self.trades = []  # List of trade dicts


def run_backtest(df, strategy_name="ma_cross", symbol="", initial_capital=1000000, **kwargs):
    """
    Run backtest on historical K-line data.

    Parameters:
        df: DataFrame with OHLCV data (index=date, columns=open/high/low/close/volume)
        strategy_name: 'ma_cross', 'rsi', 'kdj', 'ma_rsi_combined'
        initial_capital: starting capital in CNY
        **kwargs: strategy-specific parameters

    Returns:
        BacktestResult
    """
    if df.empty or 'close' not in df.columns:
        return None

    strategies = {
        'ma_cross': _strategy_ma_cross,
        'rsi': _strategy_rsi,
        'kdj': _strategy_kdj,
        'ma_rsi_combined': _strategy_ma_rsi_combined,
    }

    strategy_fn = strategies.get(strategy_name, _strategy_ma_cross)
    signals = strategy_fn(df, **kwargs)

    return _simulate_trades(df, signals, initial_capital, symbol, strategy_name)


def _strategy_ma_cross(df, short_period=5, long_period=20, **kwargs):
    """
    MA Crossover strategy: Buy when short MA crosses above long MA,
    Sell when short MA crosses below long MA.
    """
    signals = []
    short_ma = df['close'].rolling(window=short_period).mean()
    long_ma = df['close'].rolling(window=long_period).mean()

    prev_short = None
    prev_long = None

    for i in range(len(df)):
        curr_short = short_ma.iloc[i]
        curr_long = long_ma.iloc[i]

        if pd.isna(curr_short) or pd.isna(curr_long):
            signals.append(0)
            prev_short = curr_short
            prev_long = curr_long
            continue

        signal = 0
        if prev_short is not None and prev_long is not None:
            if prev_short <= prev_long and curr_short > curr_long:
                signal = 1  # Buy
            elif prev_short >= prev_long and curr_short < curr_long:
                signal = -1  # Sell

        signals.append(signal)
        prev_short = curr_short
        prev_long = curr_long

    return signals


def _strategy_rsi(df, rsi_period=14, oversold=30, overbought=70, **kwargs):
    """
    RSI strategy: Buy when RSI crosses above oversold, sell when crosses below overbought.
    """
    signals = []
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=rsi_period).mean()
    avg_loss = loss.rolling(window=rsi_period).mean()
    rs = avg_gain / avg_loss.replace(0, np.inf)
    rsi = 100 - (100 / (1 + rs))

    prev_rsi = None
    position = 0  # 0 = no position, 1 = have position

    for i in range(len(df)):
        curr_rsi = rsi.iloc[i]
        signal = 0

        if pd.isna(curr_rsi):
            signals.append(0)
            prev_rsi = curr_rsi
            continue

        if position == 0 and prev_rsi is not None:
            if prev_rsi <= oversold and curr_rsi > oversold:
                signal = 1  # Buy
                position = 1
        elif position == 1 and prev_rsi is not None:
            if prev_rsi >= overbought and curr_rsi < overbought:
                signal = -1  # Sell
                position = 0

        signals.append(signal)
        prev_rsi = curr_rsi

    # If still holding at end, force sell
    if position == 1:
        signals[-1] = -1

    return signals


def _strategy_kdj(df, period=9, **kwargs):
    """
    KDJ strategy: Buy when J crosses below 0 (oversold), sell when J crosses above 100.
    """
    signals = []
    low_min = df['low'].rolling(window=period).min()
    high_max = df['high'].rolling(window=period).max()
    rsv = (df['close'] - low_min) / (high_max - low_min).replace(0, np.inf) * 100
    rsv = rsv.fillna(50)
    k = rsv.ewm(com=2).mean()
    d = k.ewm(com=2).mean()
    j = 3 * k - 2 * d

    position = 0
    for i in range(len(df)):
        curr_j = j.iloc[i]
        signal = 0

        if pd.isna(curr_j):
            signals.append(0)
            continue

        if position == 0:
            if curr_j < 0:
                signal = 1
                position = 1
        elif curr_j > 100:
            signal = -1
            position = 0

        signals.append(signal)

    if position == 1:
        signals[-1] = -1

    return signals


def _strategy_ma_rsi_combined(df, **kwargs):
    """
    Combined MA + RSI strategy: Buy when MA bullish AND RSI oversold.
    Sell when MA bearish OR RSI overbought.
    """
    ma_signals = _strategy_ma_cross(df, **kwargs)
    rsi_signals = _strategy_rsi(df, **kwargs)

    signals = []
    for i in range(len(df)):
        # Buy only when both strategies agree
        if ma_signals[i] == 1 and rsi_signals[i] == 1:
            signals.append(1)
        elif ma_signals[i] == -1 or rsi_signals[i] == -1:
            signals.append(-1)
        else:
            signals.append(0)

    return signals


def _simulate_trades(df, signals, initial_capital, symbol, strategy_name):
    """
    Simulate trades based on signals and compute performance metrics.
    """
    result = BacktestResult()
    result.strategy_name = strategy_name
    result.symbol = symbol
    result.initial_capital = initial_capital
    result.start_date = str(df.index[0].date()) if hasattr(df.index[0], 'date') else str(df.index[0])
    result.end_date = str(df.index[-1].date()) if hasattr(df.index[-1], 'date') else str(df.index[-1])

    cash = initial_capital
    shares = 0
    has_position = False
    trades = []
    portfolio_values = []
    peak_value = initial_capital
    max_dd = 0
    max_dd_duration = 0
    current_dd_duration = 0

    for i in range(len(df)):
        price = df['close'].iloc[i]
        signal = signals[i]

        if signal == 1 and not has_position and cash > 0:
            # Buy: use up to 95% of available cash, rounded to 100-share lots
            max_shares = int(cash * 0.95 / price)
            buy_shares = (max_shares // 100) * 100
            if buy_shares >= 100:
                cost = buy_shares * price
                cash -= cost
                shares = buy_shares
                has_position = True
                trades.append({
                    'type': 'BUY',
                    'date': str(df.index[i].date()) if hasattr(df.index[i], 'date') else str(df.index[i]),
                    'price': round(price, 2),
                    'shares': buy_shares,
                    'value': round(cost, 2),
                })

        elif signal == -1 and has_position:
            # Sell
            revenue = shares * price
            # P&L = revenue - cost of shares bought
            cost_basis = trades[-1]['value'] if trades and trades[-1]['type'] == 'BUY' else 0
            profit = revenue - cost_basis
            cash += revenue
            trades.append({
                'type': 'SELL',
                'date': str(df.index[i].date()) if hasattr(df.index[i], 'date') else str(df.index[i]),
                'price': round(price, 2),
                'shares': shares,
                'value': round(revenue, 2),
                'pnl': round(profit, 2),
            })
            shares = 0
            has_position = False

        # Portfolio value
        portfolio_value = cash + shares * price
        portfolio_values.append(portfolio_value)

        # Track drawdown
        if portfolio_value > peak_value:
            peak_value = portfolio_value
            current_dd_duration = 0
        else:
            current_dd_duration += 1

        dd = (peak_value - portfolio_value) / peak_value if peak_value > 0 else 0
        if dd > max_dd:
            max_dd = dd
            max_dd_duration = current_dd_duration

    result.final_capital = round(cash, 2)
    result.total_return = round((result.final_capital - initial_capital) / initial_capital * 100, 2)

    # Annualized return
    days = (df.index[-1] - df.index[0]).days if len(df) > 1 else 1
    years = days / 365.25
    if years > 0 and result.final_capital > 0:
        result.annualized_return = round(
            ((result.final_capital / initial_capital) ** (1 / years) - 1) * 100, 2
        )

    # Sharpe ratio (annualized, assuming risk-free rate 3%)
    if len(portfolio_values) > 1:
        returns = pd.Series(portfolio_values).pct_change().dropna()
        if returns.std() > 0:
            daily_rf = 0.03 / 252
            result.sharpe_ratio = round(
                (returns.mean() - daily_rf) / returns.std() * np.sqrt(252), 2
            )

    result.max_drawdown = round(max_dd * 100, 2)
    result.max_drawdown_duration = max_dd_duration

    # Trade statistics
    sell_trades = [t for t in trades if t['type'] == 'SELL']
    result.total_trades = len(sell_trades)

    if sell_trades:
        wins = [t for t in sell_trades if t.get('pnl', 0) > 0]
        losses = [t for t in sell_trades if t.get('pnl', 0) <= 0]
        result.winning_trades = len(wins)
        result.losing_trades = len(losses)
        result.win_rate = round(len(wins) / len(sell_trades) * 100, 1) if sell_trades else 0
        result.avg_win = round(np.mean([t['pnl'] for t in wins]), 2) if wins else 0
        result.avg_loss = round(np.mean([t['pnl'] for t in losses]), 2) if losses else 0

        gross_profit = sum(t['pnl'] for t in wins)
        gross_loss = abs(sum(t['pnl'] for t in losses))
        result.profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float('inf')

    result.trades = trades

    return result


def format_backtest_report(result):
    """Format backtest result as text report"""
    if not result:
        return "No backtest data"

    lines = []
    lines.append("=" * 60)
    lines.append("  TradeMind - Backtest Report")
    lines.append(f"  Strategy:  {result.strategy_name}")
    lines.append(f"  Symbol:    {result.symbol}")
    lines.append(f"  Period:    {result.start_date} to {result.end_date}")
    lines.append(f"  Capital:   {result.initial_capital:,.0f} CNY")
    lines.append("=" * 60)
    lines.append("")
    lines.append("--- Performance ---")
    lines.append("  {:<20s}{:>15s}".format("Final Capital", f"{result.final_capital:,.2f}"))
    lines.append("  {:<20s}{:>14.2f}%".format("Total Return", result.total_return))
    lines.append("  {:<20s}{:>14.2f}%".format("Annualized Return", result.annualized_return))
    lines.append("  {:<20s}{:>15.2f}".format("Sharpe Ratio", result.sharpe_ratio))
    lines.append("  {:<20s}{:>14.2f}%".format("Max Drawdown", result.max_drawdown))
    lines.append("  {:<20s}{:>10d} days".format("Max DD Duration", result.max_drawdown_duration))
    lines.append("")
    lines.append("--- Trade Stats ---")
    lines.append("  {:<20s}{:>15d}".format("Total Trades", result.total_trades))
    lines.append("  {:<20s}{:>15d}".format("Winning", result.winning_trades))
    lines.append("  {:<20s}{:>15d}".format("Losing", result.losing_trades))
    lines.append("  {:<20s}{:>14.1f}%".format("Win Rate", result.win_rate))
    lines.append("  {:<20s}{:>15,.2f}".format("Avg Win", result.avg_win))
    lines.append("  {:<20s}{:>15,.2f}".format("Avg Loss", result.avg_loss))
    lines.append("  {:<20s}{:>15.2f}".format("Profit Factor", result.profit_factor))

    if result.trades:
        lines.append("")
        lines.append("--- Trade History (last 10) ---")
        for t in result.trades[-10:]:
            if t['type'] == 'SELL':
                lines.append("  {} SELL {:.2f} x{} PnL={:+,.2f}".format(
                    t['date'], t['price'], t['shares'], t.get('pnl', 0)))
            else:
                lines.append("  {} BUY  {:.2f} x{}".format(t['date'], t['price'], t['shares']))

    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)
