
"""
LLM Advisor — DeepSeek-powered stock analysis engine.
Fetches historical data via baostock, stores locally as parquet,
builds structured context, and calls DeepSeek API for analysis.
"""

import os
import json
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ─── Config ─────────────────────────────────────────────────
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api_config.json")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# Default DeepSeek API settings
DEEPSEEK_BASE = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"  # V3


def load_config():
    """Load API config from local file."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


def save_config(cfg):
    """Save API config to local file."""
    with open(CONFIG_PATH, 'w') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ─── Data Pipeline ──────────────────────────────────────────

def fetch_history(symbol, start_date=None, end_date=None, force_refresh=False):
    """
    Download full historical K-line data from baostock.
    Caches to data/history/{symbol}.csv.
    
    Returns: DataFrame with columns: date,open,high,low,close,volume,amount
    """
    import baostock as bs
    import os

    os.makedirs(os.path.join(DATA_DIR, "history"), exist_ok=True)
    cache_path = os.path.join(DATA_DIR, "history", f"{symbol}.csv")

    # Return cached if fresh enough (today)
    if not force_refresh and os.path.exists(cache_path):
        try:
            cached = pd.read_csv(cache_path)
            cached['date'] = pd.to_datetime(cached['date'])
            if len(cached) > 0:
                last_date = str(cached['date'].max())[:10]
                if last_date >= datetime.now().strftime('%Y-%m-%d'):
                    return cached
        except Exception:
            pass  # cache corrupted, re-fetch

    # Convert symbol to baostock format
    clean = symbol.replace('.SZ', '').replace('.SH', '').replace('.BJ', '')
    if clean.startswith('6'):
        bs_symbol = 'sh.' + clean
    elif clean.startswith(('0', '3')):
        bs_symbol = 'sz.' + clean
    else:
        bs_symbol = 'sz.' + clean

    # Date range
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=365 * 3)).strftime('%Y-%m-%d')

    # Login and query
    bs.login()
    try:
        fields = 'date,open,high,low,close,volume,amount,turn,peTTM,pbMRQ'
        rs = bs.query_history_k_data_plus(
            bs_symbol, fields,
            start_date=start_date, end_date=end_date,
            frequency='d', adjustflag='3'  # 后复权
        )

        rows = []
        while rs.next():
            rows.append(rs.get_row_data())

        df = pd.DataFrame(rows, columns=rs.fields) if rows else pd.DataFrame()

        if not df.empty:
            # Type conversion
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'turn', 'peTTM', 'pbMRQ']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            df['date'] = pd.to_datetime(df['date'])

            # Save cache
            df.to_csv(cache_path, index=False)

    finally:
        bs.logout()

    return df


def fetch_news(symbol, limit=30):
    """Get recent news for symbol. Uses existing news module."""
    try:
        from data.news import get_stock_news
        articles = get_stock_news(symbol, limit=limit)
        return articles
    except Exception:
        return []


def get_fundamentals(symbol):
    """Get latest fundamental data."""
    try:
        from data.basic import get_stock_basic
        return get_stock_basic(symbol)
    except Exception:
        return {}


# ─── Indicator Computation ──────────────────────────────────

def compute_indicators(df):
    """Compute all technical indicators from OHLCV dataframe."""
    if df.empty or 'close' not in df.columns:
        return {}

    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    volume = df['volume'].values if 'volume' in df.columns else np.zeros(len(close))

    n = len(close)
    if n < 20:
        return {}

    latest = {}

    # MA
    latest['ma5'] = float(np.mean(close[-5:]))
    latest['ma10'] = float(np.mean(close[-10:]))
    latest['ma20'] = float(np.mean(close[-20:]))
    latest['ma60'] = float(np.mean(close[-60:])) if n >= 60 else 0

    # Price stats
    latest['price'] = float(close[-1])
    latest['price_5d_ago'] = float(close[-5]) if n >= 5 else latest['price']
    latest['price_20d_ago'] = float(close[-20]) if n >= 20 else latest['price']
    latest['price_60d_high'] = float(np.max(high[-60:])) if n >= 60 else float(np.max(high))
    latest['price_60d_low'] = float(np.min(low[-60:])) if n >= 60 else float(np.min(low))
    latest['chg_5d'] = round((latest['price'] - latest['price_5d_ago']) / latest['price_5d_ago'] * 100, 2) if latest['price_5d_ago'] else 0
    latest['chg_20d'] = round((latest['price'] - latest['price_20d_ago']) / latest['price_20d_ago'] * 100, 2) if latest['price_20d_ago'] else 0

    # Volatility
    returns = np.diff(close[-21:]) / close[-21:-1]
    latest['volatility_20d'] = round(float(np.std(returns) * 100), 2)

    # Volume
    latest['avg_vol_5d'] = float(np.mean(volume[-5:]))
    latest['avg_vol_20d'] = float(np.mean(volume[-20:]))
    latest['vol_ratio'] = round(latest['avg_vol_5d'] / latest['avg_vol_20d'], 2) if latest['avg_vol_20d'] else 1

    # RSI(14)
    delta = np.diff(close[-15:])
    gain = np.maximum(delta, 0)
    loss = np.maximum(-delta, 0)
    avg_gain = np.mean(gain) if len(gain) > 0 else 0
    avg_loss = np.mean(loss) if len(loss) > 0 else 0.0001
    rs = avg_gain / avg_loss if avg_loss > 0 else 100
    latest['rsi'] = round(float(100 - 100 / (1 + rs)), 1)

    # MACD
    ema12 = pd.Series(close).ewm(span=12).mean().iloc[-1]
    ema26 = pd.Series(close).ewm(span=26).mean().iloc[-1]
    latest['macd'] = round(float(ema12 - ema26), 2)

    # Bollinger %B
    bb_mid = np.mean(close[-20:])
    bb_std = np.std(close[-20:])
    latest['bb_upper'] = round(float(bb_mid + 2 * bb_std), 2)
    latest['bb_lower'] = round(float(bb_mid - 2 * bb_std), 2)
    latest['boll_pct_b'] = round(float((close[-1] - bb_mid - 2*bb_std) / (4*bb_std) + 0.5), 3) if bb_std else 0.5

    # KDJ
    low_9 = np.min(low[-9:])
    high_9 = np.max(high[-9:])
    rsv = (close[-1] - low_9) / (high_9 - low_9) * 100 if high_9 != low_9 else 50
    k = rsv * 0.333 + 50 * 0.667
    d = k * 0.333 + 50 * 0.667
    j = 3 * k - 2 * d
    latest['kdj_k'] = round(float(k), 1)
    latest['kdj_d'] = round(float(d), 1)
    latest['kdj_j'] = round(float(j), 1)

    # Recent daily returns
    recent_close = close[-10:]
    daily_returns = [round(float((recent_close[i] - recent_close[i-1]) / recent_close[i-1] * 100), 2) 
                     for i in range(1, len(recent_close))]
    latest['daily_returns_10d'] = daily_returns[::-1]  # most recent first

    return latest


# ─── Context Builder ───────────────────────────────────────

def build_context(symbol):
    """
    Build a structured context blob for the LLM.
    Returns a dict with all the data needed for a quality prompt.
    """
    ctx = {"symbol": symbol, "generated_at": datetime.now().isoformat()}

    # 1. Price History
    df = fetch_history(symbol, start_date=(datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d'))
    if df.empty:
        ctx['error'] = 'No price data'
        return ctx

    ctx['history_days'] = len(df)
    ctx['date_range'] = f"{df['date'].min().strftime('%Y-%m-%d')} ~ {df['date'].max().strftime('%Y-%m-%d')}"

    # 2. Technical Indicators
    indicators = compute_indicators(df)
    ctx['indicators'] = indicators

    # 3. Recent price summary
    recent = df.tail(20)
    ctx['recent_summary'] = {
        'close': [round(float(x), 2) for x in recent['close'].tolist()],
        'volume': [int(x) for x in recent['volume'].tolist()],
        'dates': [d.strftime('%m-%d') for d in recent['date'].tolist()],
    }

    # 4. News
    try:
        articles = fetch_news(symbol, limit=15)
        ctx['news'] = [{'date': a.get('date', '?'), 'title': a.get('title', '')} for a in articles[:15]]
    except Exception:
        ctx['news'] = []

    # 5. Fundamentals
    try:
        fundamentals = get_fundamentals(symbol)
        if fundamentals:
            ctx['fundamentals'] = {
                k: v for k, v in fundamentals.items()
                if isinstance(v, (str, int, float, bool)) and not k.startswith('_')
            }
    except Exception:
        ctx['fundamentals'] = {}

    return ctx


# ─── Prompt Builder ────────────────────────────────────────

def build_prompt(ctx, question=None):
    """Build the system + user prompt from context."""
    symbol = ctx.get('symbol', '?')
    indicators = ctx.get('indicators', {})
    fundamentals = ctx.get('fundamentals', {})
    news = ctx.get('news', [])

    system = """你是一名专业的A股股票分析师。你会收到一只股票的结构化数据，请基于数据给出客观、量化的分析。

要求：
1. 先总结当前技术面状况（趋势、超买超卖、支撑阻力）
2. 再结合新闻舆情给出综合判断
3. 最后给出一个明确的短期（1-2周）操作建议：买入/持有/卖出，并说明理由
4. 用中文回答，精简但完整，控制在400字以内"""

    # Build data section
    parts = [f"## {symbol} 股票分析数据\n"]

    # Price & indicators
    price = indicators.get('price', 0)
    parts.append(f"### 行情快照")
    parts.append(f"- 最新价: {price}")
    parts.append(f"- 5日涨跌: {indicators.get('chg_5d', '?')}%")
    parts.append(f"- 20日涨跌: {indicators.get('chg_20d', '?')}%")
    parts.append(f"- 20日波动率: {indicators.get('volatility_20d', '?')}%")
    parts.append(f"- 60日区间: {indicators.get('price_60d_low', 0)} ~ {indicators.get('price_60d_high', 0)}")

    parts.append(f"\n### 技术指标")
    parts.append(f"- MA5: {indicators.get('ma5', '?')} | MA10: {indicators.get('ma10', '?')} | MA20: {indicators.get('ma20', '?')} | MA60: {indicators.get('ma60', '?')}")
    parts.append(f"- RSI(14): {indicators.get('rsi', '?')}")
    parts.append(f"- MACD: {indicators.get('macd', '?')}")
    parts.append(f"- 布林带: {indicators.get('bb_lower', 0)} ~ {indicators.get('bb_upper', 0)} (%B: {indicators.get('boll_pct_b', '?')})")
    parts.append(f"- KDJ: K={indicators.get('kdj_k', '?')} D={indicators.get('kdj_d', '?')} J={indicators.get('kdj_j', '?')}")
    parts.append(f"- 量比(5/20): {indicators.get('vol_ratio', '?')}")
    parts.append(f"- 近10日收益率: {indicators.get('daily_returns_10d', [])}")

    if fundamentals:
        parts.append(f"\n### 基本面")
        for k, v in fundamentals.items():
            if v is not None:
                parts.append(f"- {k}: {v}")

    if news:
        parts.append(f"\n### 近期新闻 ({len(news)}条)")
        for a in news[:10]:
            parts.append(f"- [{a.get('date', '?')}] {a.get('title', '')}")

    user = '\n'.join(parts)
    if question:
        user += f"\n\n### 用户提问\n{question}"

    return system, user


# ─── API Call ──────────────────────────────────────────────

def call_deepseek(system_prompt, user_prompt, api_key=None, model=None, stream=False):
    """
    Call DeepSeek API. Uses requests with proxy support.
    """
    import urllib.request
    import urllib.error

    if api_key is None:
        cfg = load_config()
        api_key = cfg.get('deepseek_api_key') or os.environ.get('DEEPSEEK_API_KEY')

    if not api_key:
        return {"error": "No API key configured. Set DEEPSEEK_API_KEY or create api_config.json"}

    if model is None:
        model = DEFAULT_MODEL

    url = f"{DEEPSEEK_BASE}/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 1200,
        "stream": stream
    }).encode('utf-8')

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
    }

    # Use proxy if available
    proxy_url = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') or 'http://127.0.0.1:10809'
    proxy_handler = urllib.request.ProxyHandler({
        'http': proxy_url,
        'https': proxy_url,
    }) if proxy_url else None

    opener = urllib.request.build_opener(proxy_handler) if proxy_handler else urllib.request.build_opener()
    req = urllib.request.Request(url, data=payload, headers=headers)

    try:
        resp = opener.open(req, timeout=60)
        result = json.loads(resp.read())
        if 'choices' in result and len(result['choices']) > 0:
            return {
                "content": result['choices'][0]['message']['content'],
                "model": result.get('model', model),
                "usage": result.get('usage', {}),
            }
        else:
            return {"error": f"API error: {result}", "raw": result}
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ''
        return {"error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"error": str(e)}


# ─── Main Entry ────────────────────────────────────────────

def analyze(symbol, question=None, api_key=None, verbose=True):
    """
    Full pipeline: gather data → build context → call LLM → return analysis.
    """
    if verbose:
        print(f"[1/3] Fetching historical data for {symbol}...")
    ctx = build_context(symbol)

    if 'error' in ctx:
        return ctx

    if verbose:
        print(f"[2/3] Building context ({ctx.get('history_days', 0)} days, "
              f"{len(ctx.get('news', []))} news, indicators computed)")
    system, user = build_prompt(ctx, question)

    if verbose:
        print(f"[3/3] Calling DeepSeek API...")
    result = call_deepseek(system, user, api_key=api_key)

    if verbose and 'content' in result:
        print(f"Done. Tokens: {result.get('usage', {})}")

    result['context'] = ctx  # attach context for reference
    return result


def analyze_report(symbol, api_key=None):
    """
    Generate a full analysis report (returns formatted string for display).
    """
    result = analyze(symbol, api_key=api_key, verbose=True)

    if 'error' in result:
        return f"Error: {result['error']}"

    content = result.get('content', '')
    usage = result.get('usage', {})

    header = f"""============================================================
  TradeMind LLM Analysis: {symbol}
  Model: {result.get('model', '?')}
  Tokens: {usage.get('total_tokens', '?')} (in:{usage.get('prompt_tokens','?')} out:{usage.get('completion_tokens','?')})
============================================================

"""
    return header + content + "\n\n" + "=" * 60


# ─── CLI ───────────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    symbol = sys.argv[1] if len(sys.argv) > 1 else '600519'
    question = sys.argv[2] if len(sys.argv) > 2 else None

    # Check API key
    cfg = load_config()
    api_key = cfg.get('deepseek_api_key') or os.environ.get('DEEPSEEK_API_KEY')

    if not api_key:
        print("DeepSeek API key not found.")
        print("Set it via: DEEPSEEK_API_KEY env var, or create api_config.json:")
        print('  {"deepseek_api_key": "sk-xxxxx"}')
        sys.exit(1)

    print(analyze_report(symbol, api_key=api_key))
