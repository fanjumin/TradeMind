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

def plotly_chart(df, indicators=None, symbol="", output_path=None, days=120,
                prediction=None, sentiment=None):
    """
    Professional multi-panel stock chart with prediction & sentiment overlay.
    
    Panels (6 rows):
      1. Candlestick + MA(5,10,20,60) + Bollinger Bands + Prediction trajectory
      2. Volume (green/red) + Volume MA
      3. MACD (12,26,9) histogram
      4. RSI (14) with overbought/oversight lines
      5. KDJ (9,3,3)
      6. Sentiment gauge (if sentiment data provided)

    Parameters:
        df: DataFrame with OHLCV
        indicators: dict from technical.py
        symbol: stock symbol
        output_path: save path
        days: recent days to show
        prediction: dict from predict_stock() — draws prediction trajectory
        sentiment: dict from analyze_social_sentiment() — draws sentiment bar
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import pandas as pd
    import numpy as np
    import os

    if df.empty or 'close' not in df.columns:
        print("No data available for chart")
        return None

    df = df.tail(days).copy()
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
        dates = df['date']
        df = df.set_index('date')
    else:
        dates = df.index

    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume'] if 'volume' in df.columns else pd.Series(0, index=df.index)

    # --- Compute indicators ---
    ma5 = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(span=14, min_periods=14).mean()
    avg_loss = loss.ewm(span=14, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9).mean()
    macd_hist = macd_line - signal_line

    bb_mid = ma20
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std

    low_n = low.rolling(9).min()
    high_n = high.rolling(9).max()
    rsv = (close - low_n) / (high_n - low_n).replace(0, np.nan) * 100
    k = rsv.ewm(span=3, min_periods=3).mean()
    d = k.ewm(span=3, min_periods=3).mean()
    j = 3 * k - 2 * d

    # Volume MA
    vol_ma5 = volume.rolling(5).mean()

    # --- Determine panel layout ---
    has_sentiment = sentiment is not None and isinstance(sentiment, dict)
    n_rows = 6 if has_sentiment else 5
    row_heights = [0.35, 0.13, 0.13, 0.13, 0.13, 0.13] if has_sentiment else [0.38, 0.15, 0.15, 0.15, 0.17]
    subplot_titles = (
        f"<b>{symbol}</b> — K线 + 均线 + 布林带",
        "成交量",
        "MACD (12,26,9)",
        "RSI (14)",
        "KDJ (9,3,3)",
    )
    if has_sentiment:
        subplot_titles += ("📊 社交情绪",)

    # --- Color scheme (dark professional) ---
    BG = '#0d1117'
    PAPER = '#0d1117'
    GRID = '#21262d'
    TEXT = '#c9d1d9'
    GREEN = '#26a69a'
    RED = '#ef5350'
    BLUE = '#42a5f5'
    YELLOW = '#ffca28'
    PURPLE = '#ab47bc'
    ORANGE = '#ff7043'
    WHITE = '#e0e0e0'

    fig = make_subplots(
        rows=n_rows, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=row_heights,
        subplot_titles=subplot_titles,
    )

    # ═══════════════════ PANEL 1: Candlestick ═══════════════════
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['open'], high=df['high'],
        low=df['low'], close=df['close'],
        name='K线',
        increasing_line_color=GREEN, decreasing_line_color=RED,
        increasing_fillcolor=GREEN, decreasing_fillcolor=RED,
        showlegend=True,
    ), row=1, col=1)

    # MAs
    for ma, name, color, width in [
        (ma5, 'MA5', '#ff6d00', 1),
        (ma10, 'MA10', '#ffab00', 1),
        (ma20, 'MA20', '#00e5ff', 1.5),
        (ma60, 'MA60', '#d500f9', 1),
    ]:
        fig.add_trace(go.Scatter(
            x=df.index, y=ma, mode='lines',
            name=name, line=dict(color=color, width=width),
            showlegend=True,
        ), row=1, col=1)

    # Bollinger Bands
    fig.add_trace(go.Scatter(
        x=df.index, y=bb_upper, mode='lines',
        name='BB Upper', line=dict(color='rgba(66,165,245,0.3)', width=0.5),
        showlegend=True,
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=bb_lower, mode='lines',
        name='BB Lower', line=dict(color='rgba(66,165,245,0.3)', width=0.5),
        fill='tonexty', fillcolor='rgba(66,165,245,0.05)',
        showlegend=True,
    ), row=1, col=1)

    # --- Prediction overlay ---
    if prediction and isinstance(prediction, dict):
        sk = prediction.get('sklearn', {})
        if sk and sk.get('predicted_price'):
            last_date = df.index[-1]
            last_close = close.iloc[-1]
            target_price = sk['predicted_price']
            pred_days = sk.get('prediction_days', 5)

            # Draw prediction arrow + target
            pred_dates = pd.date_range(last_date, periods=pred_days+2, freq='B')[1:]
            pred_line = np.linspace(last_close, target_price, pred_days+1)[1:]

            color = GREEN if sk['direction'] == 'up' else RED
            fig.add_trace(go.Scatter(
                x=list(pred_dates), y=list(pred_line),
                mode='lines+markers',
                name=f'ML预测 ({pred_days}日)',
                line=dict(color=color, width=2, dash='dot'),
                marker=dict(size=6, symbol='diamond', color=color),
                showlegend=True,
            ), row=1, col=1)

            # Confidence band
            conf = sk.get('direction_confidence', 0.65)
            band = abs(target_price - last_close) * (1 - conf) * 2
            upper_band = pred_line + band * np.linspace(0.2, 0.8, len(pred_line))
            lower_band = pred_line - band * np.linspace(0.2, 0.8, len(pred_line))
            fig.add_trace(go.Scatter(
                x=list(pred_dates), y=list(upper_band),
                mode='lines', line=dict(width=0),
                showlegend=False,
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=list(pred_dates), y=list(lower_band),
                mode='lines', line=dict(width=0),
                fill='tonexty', fillcolor=f'rgba({ "38,166,154" if color==GREEN else "239,83,80" },0.1)',
                name=f'置信区间 ({conf:.0%})',
                showlegend=True,
            ), row=1, col=1)

    # ═══════════════════ PANEL 2: Volume ═══════════════════
    vol_colors = [GREEN if close.iloc[i] >= df['open'].iloc[i] else RED
                  for i in range(len(df))]
    fig.add_trace(go.Bar(
        x=df.index, y=volume, name='成交量',
        marker_color=vol_colors, marker_line_width=0,
        showlegend=False,
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=vol_ma5, mode='lines',
        name='VOL MA5', line=dict(color=YELLOW, width=1),
        showlegend=False,
    ), row=2, col=1)

    # ═══════════════════ PANEL 3: MACD ═══════════════════
    macd_colors = [GREEN if v >= 0 else RED for v in macd_hist]
    fig.add_trace(go.Bar(
        x=df.index, y=macd_hist, name='MACD Hist',
        marker_color=macd_colors, marker_line_width=0,
        showlegend=False,
    ), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=macd_line, mode='lines',
        name='MACD', line=dict(color=BLUE, width=1.5),
        showlegend=False,
    ), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=signal_line, mode='lines',
        name='Signal', line=dict(color=ORANGE, width=1),
        showlegend=False,
    ), row=3, col=1)
    # Zero line
    fig.add_hline(y=0, line_dash="solid", line_color=GRID, line_width=0.5, row=3, col=1)

    # ═══════════════════ PANEL 4: RSI ═══════════════════
    fig.add_trace(go.Scatter(
        x=df.index, y=rsi, mode='lines',
        name='RSI', line=dict(color=PURPLE, width=1.5),
        fill='tozeroy', fillcolor='rgba(171,71,188,0.05)',
        showlegend=False,
    ), row=4, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color=RED, line_width=0.8,
                  annotation_text="超买 70", annotation_position="right", row=4, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color=GREEN, line_width=0.8,
                  annotation_text="超卖 30", annotation_position="right", row=4, col=1)
    fig.add_hline(y=50, line_dash="solid", line_color=GRID, line_width=0.5, row=4, col=1)

    # ═══════════════════ PANEL 5: KDJ ═══════════════════
    fig.add_trace(go.Scatter(
        x=df.index, y=k, mode='lines',
        name='K', line=dict(color=WHITE, width=1),
        showlegend=False,
    ), row=5, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=d, mode='lines',
        name='D', line=dict(color=YELLOW, width=1),
        showlegend=False,
    ), row=5, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=j, mode='lines',
        name='J', line=dict(color=PURPLE, width=0.8, dash='dot'),
        showlegend=False,
    ), row=5, col=1)
    fig.add_hline(y=80, line_dash="dash", line_color=RED, line_width=0.5, row=5, col=1)
    fig.add_hline(y=20, line_dash="dash", line_color=GREEN, line_width=0.5, row=5, col=1)

    # ═══════════════════ PANEL 6: Sentiment ═══════════════════
    if has_sentiment:
        ss = sentiment.get('social_sentiment', sentiment)
        score = ss.get('overall_score', 0)
        label = ss.get('overall_label', 'neutral')
        post_count = ss.get('post_count', ss.get('article_count', 0))

        # Sentiment gauge as horizontal bar
        bar_color = GREEN if label == 'bullish' else (RED if label == 'bearish' else YELLOW)
        score_norm = max(-1, min(1, score))  # clamp to [-1, 1]

        fig.add_trace(go.Bar(
            x=[score_norm], y=['情绪'],
            orientation='h', name='社交情绪',
            marker_color=bar_color,
            text=[f"{score:+.2f} ({label})  |  {post_count}条帖子"],
            textposition='inside', textfont=dict(color='black', size=12),
            width=0.4,
            showlegend=False,
        ), row=6, col=1)

        # Add reference zone
        fig.add_vrect(x0=-1, x1=-0.3, fillcolor='rgba(239,83,80,0.08)', line_width=0,
                      row=6, col=1)
        fig.add_vrect(x0=-0.3, x1=0.3, fillcolor='rgba(255,202,40,0.08)', line_width=0,
                      row=6, col=1)
        fig.add_vrect(x0=0.3, x1=1, fillcolor='rgba(38,166,154,0.08)', line_width=0,
                      row=6, col=1)
        fig.add_vline(x=0, line_dash="solid", line_color=GRID, line_width=0.5,
                      row=6, col=1)
        fig.update_xaxes(range=[-1.1, 1.1], row=6, col=1,
                         tickvals=[-1, -0.5, 0, 0.5, 1],
                         ticktext=['🔴 看空', '-0.5', '中性', '+0.5', '🟢 看多'])

    # ═══════════════════ Layout ═══════════════════
    title_text = f"<b>{symbol}</b> 技术分析"
    if prediction:
        sk = prediction.get('sklearn', {})
        if sk:
            arrow = '↗' if sk['direction'] == 'up' else '↘'
            title_text += (f"  |  ML预测: {arrow} {sk['predicted_price']:.2f} "
                          f"({sk['predicted_return']:+.2%})  准确率{sk['direction_confidence']:.0%}")

    fig.update_layout(
        title=dict(text=title_text, font=dict(size=16, color=TEXT), x=0.5),
        template='plotly_dark',
        paper_bgcolor=PAPER,
        plot_bgcolor=BG,
        font=dict(color=TEXT, size=10),
        height=200 * n_rows,
        hovermode='x unified',
        legend=dict(
            orientation='h', yanchor='top', y=1.12, xanchor='center', x=0.5,
            font=dict(size=9),
        ),
        margin=dict(l=10, r=20, t=70 if prediction else 50, b=10),
        xaxis=dict(showgrid=True, gridcolor=GRID, gridwidth=0.5),
        dragmode='pan',
    )

    # Y-axis labels
    fig.update_yaxes(title_text="价格", row=1, col=1, showgrid=True, gridcolor=GRID)
    fig.update_yaxes(title_text="量", row=2, col=1, showgrid=True, gridcolor=GRID)
    fig.update_yaxes(title_text="MACD", row=3, col=1, showgrid=True, gridcolor=GRID)
    fig.update_yaxes(title_text="RSI", row=4, col=1, showgrid=True, gridcolor=GRID, range=[0, 100])
    fig.update_yaxes(title_text="KDJ", row=5, col=1, showgrid=True, gridcolor=GRID, range=[0, 100])

    fig.update_xaxes(showgrid=True, gridcolor=GRID, rangeslider_visible=False)

    # --- Save ---
    if output_path is None:
        chart_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'charts')
        os.makedirs(chart_dir, exist_ok=True)
        output_path = os.path.join(chart_dir, f'{symbol}_chart.html')

    fig.write_html(output_path, include_plotlyjs='cdn', full_html=True)
    return output_path

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
