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
