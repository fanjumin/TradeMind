"""
Text-based and SVG chart visualization for stock data.
"""


def text_kline_chart(df, width=60, height=20):
    """
    Render a text-based K-line (candlestick) chart in the terminal.
    Uses unicode block characters for visual representation.
    """
    if df.empty or 'close' not in df.columns:
        return "No data"

    # Get last N candles to fit width
    n = min(width, len(df))
    recent = df.tail(n).reset_index(drop=True)

    prices = []
    for i in range(n):
        prices.append(recent['high'].iloc[i])
        prices.append(recent['low'].iloc[i])

    min_p = min(prices)
    max_p = max(prices)
    if max_p == min_p:
        max_p = min_p + 1

    def price_to_row(p):
        return int((1 - (p - min_p) / (max_p - min_p)) * (height - 1))

    # Build grid
    grid = [[' '] * n for _ in range(height)]

    for i in range(n):
        o = recent['open'].iloc[i]
        c = recent['close'].iloc[i]
        h = recent['high'].iloc[i]
        l = recent['low'].iloc[i]

        is_up = c >= o

        o_row = price_to_row(o)
        c_row = price_to_row(c)
        h_row = price_to_row(h)
        l_row = price_to_row(l)

        body_top = min(o_row, c_row)
        body_bot = max(o_row, c_row)

        # Wick
        for r in range(h_row, l_row + 1):
            grid[r][i] = '|'

        # Body (overwrite wick)
        for r in range(body_top, body_bot + 1):
            if is_up:
                grid[r][i] = '#' if body_bot - body_top > 0 else '|'
            else:
                grid[r][i] = '@' if body_bot - body_top > 0 else '|'

    # Build output
    lines = []
    # Price scale
    lines.append("Price Scale:")
    for r in range(height):
        row_chars = ''.join(grid[r])
        if r == 0:
            label = '%8.2f ' % max_p
        elif r == height - 1:
            label = '%8.2f ' % min_p
        elif r == height // 2:
            mid = (max_p + min_p) / 2
            label = '%8.2f ' % mid
        else:
            label = '         '
        lines.append(label + '|' + row_chars)

    lines.append('         +' + '-' * n)

    # Date labels
    date_str = ''
    step = max(1, n // 5)
    for i in range(0, n, step):
        d = recent['date'].iloc[i] if 'date' in recent.columns else recent.index[i]
        date_label = str(d)[:10] if hasattr(d, 'strftime') else str(d)[:10]
        date_str += date_label + ' ' * (step - len(date_label))
    lines.append('         ' + date_str[:n])

    lines.append('')
    lines.append('  Legend: # = bullish candle  @ = bearish candle  | = wick')

    return '\n'.join(lines)


def text_indicator_chart(indicators, width=50):
    """
    Render text-based indicator visualization.
    Shows RSI, MACD, and Bollinger Bands as horizontal bars.
    """
    lines = []

    # RSI bar
    rsi = indicators.get('rsi', 50)
    rsi_bar = _make_hbar(rsi, 0, 100, width, thresholds=[(20, 'oversold'), (30, 'weak'), (70, 'strong'), (80, 'overbought')])
    lines.append(f"RSI(14) [{rsi:.1f}]")
    lines.append(f"  0{rsi_bar}100")
    lines.append("   |-----|-----|-----|-----|")
    lines.append("  oversold     neutral    overbought")

    # MACD
    macd = indicators.get('macd', 0)
    macd_bar = _make_hbar_centered(macd, width)
    lines.append(f"\nMACD [{macd:+.2f}]")
    lines.append(f"  {macd_bar}")

    # Bollinger Bands
    boll_pos = indicators.get('boll_position', 'middle')
    pct_b = indicators.get('boll_pct_b', 0.5)
    boll_bar = _make_hbar(pct_b * 100, 0, 100, width)
    lines.append(f"\nBollinger %B [{pct_b:.3f}] ({boll_pos})")
    lines.append(f"  0{boll_bar}100")
    lines.append("   |-----|-----|-----|-----|")
    lines.append("  lower    mid    upper    extreme")

    # KDJ
    k = indicators.get('k', 50)
    d = indicators.get('d', 50)
    j = indicators.get('j', 50)
    lines.append(f"\nKDJ: K={k:.1f} D={d:.1f} J={j:.1f}")
    k_bar = _make_hbar(k, 0, 100, width // 3)
    d_bar = _make_hbar(d, 0, 100, width // 3)
    j_bar = _make_hbar(j, 0, 100, width // 3)
    lines.append(f"  K: 0{k_bar}100")
    lines.append(f"  D: 0{d_bar}100")
    lines.append(f"  J: 0{j_bar}100")

    return '\n'.join(lines)


def _make_hbar(value, min_val, max_val, width, thresholds=None):
    """Make a horizontal bar showing value position"""
    pos = int((value - min_val) / (max_val - min_val) * width) if max_val != min_val else 0
    pos = max(0, min(width, pos))
    bar = '-' * pos + '*' + '-' * (width - pos)
    return bar


def _make_hbar_centered(value, width):
    """Make a horizontal bar centered at 0"""
    half = width // 2
    if value >= 0:
        pos = int(value / max(abs(value), 1) * half)
        pos = min(half, pos)
        bar = ' ' * half + '=' * pos + '>' + '-' * (half - pos)
    else:
        pos = int(abs(value) / max(abs(value), 1) * half)
        pos = min(half, pos)
        bar = '-' * (half - pos) + '<' + '=' * pos + ' ' * half
    return bar


def generate_svg_chart(df, indicators, symbol, output_path=None):
    """
    Generate a simple SVG chart of price + moving averages.
    Returns SVG as string or writes to file.
    """
    if df.empty:
        return ""

    n = min(60, len(df))
    recent = df.tail(n)

    width = 800
    height = 400
    margin = 60
    chart_w = width - margin * 2
    chart_h = height - margin * 2

    # Data
    closes = recent['close'].tolist()
    ma5s = recent.get('MA5', [0] * n).tolist()
    ma20s = recent.get('MA20', [0] * n).tolist()

    all_vals = closes + ma5s + ma20s
    min_v = min(all_vals)
    max_v = max(all_vals)
    if max_v == min_v:
        max_v = min_v + 1

    def x(i):
        return margin + (i / (n - 1)) * chart_w

    def y(v):
        return margin + chart_h - ((v - min_v) / (max_v - min_v)) * chart_h

    # Build SVG
    svg_parts = []
    svg_parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    svg_parts.append(f'<rect width="{width}" height="{height}" fill="#1a1a2e"/>')

    # Title
    svg_parts.append(f'<text x="{width/2}" y="30" fill="#e0e0e0" font-size="16" text-anchor="middle" font-family="monospace">{symbol} - Price Chart (last {n} days)</text>')

    # Grid lines
    for i in range(5):
        val = min_v + (max_v - min_v) * i / 4
        svg_parts.append(f'<line x1="{margin}" y1="{y(val)}" x2="{width-margin}" y2="{y(val)}" stroke="#333" stroke-width="0.5"/>')
        svg_parts.append(f'<text x="{margin-5}" y="{y(val)+4}" fill="#888" font-size="10" text-anchor="end" font-family="monospace">{val:.0f}</text>')

    # MA lines
    def make_line_path(values, color):
        points = []
        for i, v in enumerate(values):
            if v > 0:
                points.append(f'{x(i)},{y(v)}')
        return f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="1.5"/>'

    svg_parts.append(make_line_path(ma5s, '#ffaa00'))
    svg_parts.append(make_line_path(ma20s, '#00aaff'))

    # Price line
    price_points = [f'{x(i)},{y(c)}' for i, c in enumerate(closes)]
    svg_parts.append(f'<polyline points="{" ".join(price_points)}" fill="none" stroke="#00ff88" stroke-width="2"/>')

    # Legend
    legend_y = height - 20
    svg_parts.append(f'<line x1="{margin}" y1="{legend_y}" x2="{margin+30}" y2="{legend_y}" stroke="#00ff88" stroke-width="2"/>')
    svg_parts.append(f'<text x="{margin+35}" y="{legend_y+4}" fill="#00ff88" font-size="10" font-family="monospace">Price</text>')
    svg_parts.append(f'<line x1="{margin+100}" y1="{legend_y}" x2="{margin+130}" y2="{legend_y}" stroke="#ffaa00" stroke-width="1.5"/>')
    svg_parts.append(f'<text x="{margin+135}" y="{legend_y+4}" fill="#ffaa00" font-size="10" font-family="monospace">MA5</text>')
    svg_parts.append(f'<line x1="{margin+200}" y1="{legend_y}" x2="{margin+230}" y2="{legend_y}" stroke="#00aaff" stroke-width="1.5"/>')
    svg_parts.append(f'<text x="{margin+235}" y="{legend_y+4}" fill="#00aaff" font-size="10" font-family="monospace">MA20</text>')

    svg_parts.append('</svg>')

    svg = '\n'.join(svg_parts)

    if output_path:
        with open(output_path, 'w') as f:
            f.write(svg)

    return svg


# ============================================================
#  Plotly Interactive Chart (added Phase 1 visualization)
# ============================================================

def plotly_chart(df, indicators=None, symbol="", output_path=None, days=120):
    """
    Generate interactive Plotly candlestick chart with indicators.

    Parameters:
        df: DataFrame with OHLCV data (must have 'date','open','close','high','low','volume')
        indicators: dict from technical.py (optional; auto-computed if None)
        symbol: stock symbol for title
        output_path: where to save HTML (default: charts/{symbol}_chart.html)
        days: number of recent days to display

    Returns:
        str: path to saved HTML file
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import pandas as pd
    import numpy as np
    import os

    if df.empty or 'close' not in df.columns:
        print("No data available for chart")
        return None

    # Prepare data - take last N days
    df = df.tail(days).copy()
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
        dates = df['date']
        df = df.set_index('date')
    else:
        dates = df.index

    # --- Compute indicators from data ---
    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume'] if 'volume' in df.columns else pd.Series([0]*len(df))

    # MAs
    ma5 = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(span=14, min_periods=14).mean()
    avg_loss = loss.ewm(span=14, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    # MACD
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9).mean()
    macd_hist = macd_line - signal_line

    # Bollinger Bands
    bb_mid = ma20
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std

    # KDJ
    low_n = low.rolling(9).min()
    high_n = high.rolling(9).max()
    rsv = (close - low_n) / (high_n - low_n).replace(0, np.nan) * 100
    k = rsv.ewm(span=3, min_periods=3).mean()
    d = k.ewm(span=3, min_periods=3).mean()
    j = 3 * k - 2 * d

    # Support/Resistance from indicators dict if available
    resistance = indicators.get('resistance', None) if indicators else None
    support = indicators.get('support', None) if indicators else None
    pivot = indicators.get('pivot', None) if indicators else None

    # --- Build figure ---
    fig = make_subplots(
        rows=5, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.4, 0.15, 0.15, 0.15, 0.15],
        subplot_titles=(
            f"{symbol} - K线图",
            "成交量",
            f"RSI(14)",
            "MACD(12,26,9)",
            "KDJ(9,3,3)"
        )
    )

    # Colors
    COLORS = {
        'bg': '#0d1116',
        'plot_bg': '#161b22',
        'grid': '#2a2e35',
        'green': '#26a69a',
        'red': '#ef5350',
        'ma5': '#ffaa00',
        'ma10': '#ff6b35',
        'ma20': '#00aaff',
        'ma60': '#e040fb',
        'bb': '#888888',
        'volume_up': '#26a69a',
        'volume_down': '#ef5350',
    }

    # --- Row 1: Candlestick ---
    fig.add_trace(go.Candlestick(
        x=dates,
        open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        name='K线',
        increasing_line_color=COLORS['green'],
        decreasing_line_color=COLORS['red'],
    ), row=1, col=1)

    # Moving Averages
    for ma_name, ma_data, color in [
        ('MA5', ma5, COLORS['ma5']),
        ('MA10', ma10, COLORS['ma10']),
        ('MA20', ma20, COLORS['ma20']),
        ('MA60', ma60, COLORS['ma60']),
    ]:
        fig.add_trace(go.Scatter(
            x=dates, y=ma_data, mode='lines',
            line=dict(width=1.2, color=color),
            name=ma_name,
        ), row=1, col=1)

    # Bollinger Bands
    fig.add_trace(go.Scatter(
        x=dates, y=bb_upper, mode='lines',
        line=dict(width=0.8, color=COLORS['bb'], dash='dash'),
        name='BB Upper', showlegend=True,
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=dates, y=bb_lower, mode='lines',
        line=dict(width=0.8, color=COLORS['bb'], dash='dash'),
        name='BB Lower', fill='tonexty', fillcolor='rgba(128,128,128,0.05)',
    ), row=1, col=1)

    # Support/Resistance
    if resistance:
        fig.add_hline(y=resistance, line=dict(color='red', width=1, dash='dot'),
                      row=1, col=1, annotation_text=f'R:{resistance:.2f}')
    if support:
        fig.add_hline(y=support, line=dict(color='green', width=1, dash='dot'),
                      row=1, col=1, annotation_text=f'S:{support:.2f}')
    if pivot:
        fig.add_hline(y=pivot, line=dict(color='gray', width=1, dash='dot'),
                      row=1, col=1)

    # --- Row 2: Volume ---
    vol_colors = [COLORS['volume_up'] if c >= o else COLORS['volume_down'] 
                  for c, o in zip(df['close'], df['open'])]
    fig.add_trace(go.Bar(
        x=dates, y=volume, name='成交量',
        marker_color=vol_colors,
        marker_line_width=0,
    ), row=2, col=1)

    # Volume MA
    vol_ma5 = volume.rolling(5).mean()
    fig.add_trace(go.Scatter(
        x=dates, y=vol_ma5, mode='lines',
        line=dict(width=1, color='#ffcc80'),
        name='量MA5',
    ), row=2, col=1)

    # --- Row 3: RSI ---
    fig.add_trace(go.Scatter(
        x=dates, y=rsi, mode='lines',
        line=dict(width=1.5, color='#b388ff'),
        name='RSI',
    ), row=3, col=1)
    fig.add_hline(y=70, line=dict(color='red', width=1, dash='dash'), row=3, col=1)
    fig.add_hline(y=30, line=dict(color='green', width=1, dash='dash'), row=3, col=1)
    fig.add_hline(y=50, line=dict(color='#555', width=0.5, dash='dot'), row=3, col=1)

    # --- Row 4: MACD ---
    fig.add_trace(go.Scatter(
        x=dates, y=macd_line, mode='lines',
        line=dict(width=1.2, color='#82b1ff'),
        name='MACD',
    ), row=4, col=1)
    fig.add_trace(go.Scatter(
        x=dates, y=signal_line, mode='lines',
        line=dict(width=1, color='#ff8a80'),
        name='Signal',
    ), row=4, col=1)
    # MACD Histogram
    hist_colors = [COLORS['green'] if v >= 0 else COLORS['red'] for v in macd_hist]
    fig.add_trace(go.Bar(
        x=dates, y=macd_hist, name='Histogram',
        marker_color=hist_colors, marker_line_width=0,
    ), row=4, col=1)
    fig.add_hline(y=0, line=dict(color='#555', width=0.5), row=4, col=1)

    # --- Row 5: KDJ ---
    fig.add_trace(go.Scatter(
        x=dates, y=k, mode='lines',
        line=dict(width=1.2, color='#80cbc4'),
        name='K',
    ), row=5, col=1)
    fig.add_trace(go.Scatter(
        x=dates, y=d, mode='lines',
        line=dict(width=1.2, color='#ffab91'),
        name='D',
    ), row=5, col=1)
    fig.add_trace(go.Scatter(
        x=dates, y=j, mode='lines',
        line=dict(width=1, color='#c5e1a5', dash='dot'),
        name='J',
    ), row=5, col=1)
    fig.add_hline(y=80, line=dict(color='red', width=1, dash='dash'), row=5, col=1)
    fig.add_hline(y=20, line=dict(color='green', width=1, dash='dash'), row=5, col=1)

    # --- Layout ---
    # Build title line
    title_lines = [f"<b>{symbol}</b>"]
    if len(df) > 0:
        last_close = float(df['close'].iloc[-1])
        prev_close = float(df['close'].iloc[-2]) if len(df) > 1 else last_close
        chg = last_close - prev_close
        chg_pct = (chg / prev_close * 100) if prev_close else 0
        chg_color = 'green' if chg >= 0 else 'red'
        title_lines.append(
            f' <span style="color:{chg_color}">'
            f'{last_close:.2f} ({chg:+.2f} / {chg_pct:+.2f}%)</span>'
        )
    # Add indicators summary
    if indicators:
        rsi_v = indicators.get('rsi', rsi.iloc[-1] if not rsi.empty else None)
        kdj_j = indicators.get('j', j.iloc[-1] if not j.empty else None)
        if rsi_v is not None:
            title_lines.append(f" | RSI:{rsi_v:.1f}")
        if kdj_j is not None:
            title_lines.append(f" | J:{kdj_j:.1f}")

    fig.update_layout(
        title=' '.join(title_lines),
        xaxis_rangeslider_visible=False,
        template='plotly_dark',
        paper_bgcolor=COLORS['bg'],
        plot_bgcolor=COLORS['plot_bg'],
        height=900,
        hovermode='x unified',
        legend=dict(
            orientation='h', yanchor='top', y=1.12, xanchor='left', x=0,
            bgcolor='rgba(0,0,0,0)', font=dict(size=10)
        ),
        margin=dict(l=60, r=40, t=80, b=40),
    )

    # Update axes
    fig.update_xaxes(showgrid=True, gridcolor=COLORS['grid'], zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor=COLORS['grid'], zeroline=False)

    # Row-specific y-axis labels
    fig.update_yaxes(title_text="价格", row=1, col=1)
    fig.update_yaxes(title_text="量", row=2, col=1)
    fig.update_yaxes(title_text="RSI", row=3, col=1, range=[0, 100])
    fig.update_yaxes(title_text="MACD", row=4, col=1)
    fig.update_yaxes(title_text="KDJ", row=5, col=1, range=[0, 100])

    # --- Save ---
    if output_path is None:
        os.makedirs("charts", exist_ok=True)
        output_path = f"charts/{symbol}_chart.html"

    fig.write_html(output_path, include_plotlyjs='cdn', full_html=True)
    print(f"Chart saved: {output_path}")

    return output_path


# Quick CLI entry for direct testing
def _plotly_cli():
    import sys
    from data.price import get_price_data
    from analysis.technical import get_trend_detail

    if len(sys.argv) < 2:
        print("Usage: python visualization.py <symbol>")
        return

    symbol = sys.argv[1]
    df = get_price_data(symbol, datalen=200)
    if df.empty:
        print(f"No data for {symbol}")
        return

    indicators = get_trend_detail(df)
    plotly_chart(df, indicators=indicators, symbol=symbol)

if __name__ == '__main__':
    _plotly_cli()
