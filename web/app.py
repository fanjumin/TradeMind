"""
TradeMind Web Dashboard - Real-time A-Stock Market Tracker
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

import json
import time
from datetime import datetime
from flask import Flask, render_template, jsonify, request

from data.price import get_latest_price, get_price_data
from data.index import get_all_indices_status
from data.fund import get_fund_flow
from data.basic import get_basic_info, get_basic_score
from analysis.technical import get_trend, get_trend_detail
from analysis.scoring import get_score, get_signal, get_signal_cn
from backtest import run_backtest
from predict import predict_price
from portfolio import PortfolioManager, get_default_portfolio
from analysis.predict import predict_stock, print_prediction
from analysis.social_sentiment import analyze_social_sentiment
from analysis.sentiment import get_sentiment_for_stock
from visualization import plotly_chart
from data.price import get_price_data as fetch_price_data
from analysis.technical import get_trend_detail as fetch_indicators

app = Flask(__name__)
pm = PortfolioManager()

# Register API v1 blueprint
from web.api_v1 import api_v1, OPENAPI_SPEC, SWAGGER_HTML
app.register_blueprint(api_v1)

@app.route('/api/docs')
def api_docs_global():
    return SWAGGER_HTML

@app.route('/api/openapi.json')
def api_openapi_global():
    from flask import jsonify
    return jsonify(OPENAPI_SPEC)

@app.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

def safe_json(obj):
    """Recursively replace infinity/NaN with safe values"""
    if isinstance(obj, dict):
        return {k: safe_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [safe_json(v) for v in obj]
    elif isinstance(obj, float):
        if obj == float('inf'): return 999.0
        if obj == float('-inf'): return -999.0
        if obj != obj: return 0  # NaN
        return obj
    return obj

def safe_jsonify(obj, *args, **kwargs):
    return jsonify(safe_json(obj), *args, **kwargs)

# Popular AI / tech / growth stocks for dashboard
DEFAULT_STOCKS = [
    {"code": "600519", "name": "贵州茅台"},
    {"code": "000858", "name": "五粮液"},
    {"code": "002594", "name": "比亚迪"},
    {"code": "300750", "name": "宁德时代"},
    {"code": "000001", "name": "平安银行"},
    {"code": "600036", "name": "招商银行"},
    {"code": "300059", "name": "东方财富"},
    {"code": "002475", "name": "立讯精密"},
    {"code": "601012", "name": "隆基绿能"},
    {"code": "002230", "name": "科大讯飞"},
    {"code": "688981", "name": "中芯国际"},
    {"code": "002049", "name": "紫光国微"},
]

# Track last data fetch times to avoid too-frequent calls
_cache = {}

def _cached(key, fn, ttl=10):
    now = time.time()
    if key in _cache:
        data, ts = _cache[key]
        if now - ts < ttl:
            return data
    result = fn()
    _cache[key] = (result, now)
    return result


@app.route("/analyze")
def analyze_page():
    """Quick stock analysis page."""
    return render_template("analyze.html")


@app.route("/chart/<symbol>")
def serve_chart(symbol):
    """Serve chart HTML directly."""
    try:
        df = fetch_price_data(symbol.upper(), datalen=200)
        if df.empty:
            return f"<h3>No data for {symbol}</h3>", 404
        indicators = fetch_indicators(df)
        path = plotly_chart(df, indicators=indicators, symbol=symbol.upper(), days=120)
        if path and os.path.exists(path):
            return open(path).read()
        return f"<h3>Chart not found</h3>", 404
    except Exception as e:
        return f"<h3>Error: {e}</h3>", 500


@app.route("/trade")
def trade_page():
    return render_template("trade.html")

@app.route("/strategies")
def strategies_page():
    return render_template("strategies.html")

@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/indices")
def api_indices():
    def _fetch():
        data = get_all_indices_status()
        return data
    result = _cached("indices", _fetch, ttl=15)
    return jsonify(safe_json(result))


@app.route("/api/stocks")
def api_stocks():
    """Get real-time data for all default stocks"""
    def _fetch():
        results = []
        for s in DEFAULT_STOCKS:
            try:
                info = get_latest_price(s["code"])
                if info and "error" not in info:
                    info["watch_name"] = s["name"]
                    results.append(info)
                time.sleep(0.15)
            except:
                pass
        return results
    result = _cached("stocks", _fetch, ttl=10)
    return jsonify(safe_json(result))


@app.route("/api/stock/<symbol>")
def api_stock_detail(symbol):
    """Get detailed analysis for a single stock"""
    try:
        info = get_latest_price(symbol)
        if not info or "error" in info:
            return jsonify({"error": "Stock not found"}), 404

        # K-line data for chart
        df = get_price_data(symbol, datalen=120)
        kline_data = []
        if not df.empty:
            for _, row in df.iterrows():
                d = row.name
                if hasattr(d, "strftime"):
                    ds = d.strftime("%Y-%m-%d")
                else:
                    ds = str(d)[:10]
                kline_data.append({
                    "time": ds,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0)),
                })

        # Technical analysis
        trend = get_trend(df)
        indicators = get_trend_detail(df)

        # Fund flow
        fund_total, fund_detail = get_fund_flow(symbol)

        # Basic info
        basic = get_basic_info(symbol)
        basic_score, basic_reasons = get_basic_score(basic)

        # Score & signal
        score = get_score(trend, fund_total, basic_score, indicators)
        signal = get_signal(score)

        return jsonify({
            "info": info,
            "kline": kline_data,
            "trend": trend,
            "indicators": indicators,
            "fund_total": round(float(fund_total), 0),
            "fund_detail": fund_detail,
            "basic": basic,
            "basic_score": basic_score,
            "basic_reasons": basic_reasons,
            "total_score": score,
            "signal": signal,
            "signal_cn": get_signal_cn(signal),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/search")
def api_search():
    """Search stocks by code or name"""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    # Use the default list + search
    results = []
    for s in DEFAULT_STOCKS:
        if q in s["code"] or q in s["name"]:
            results.append(s)
    return jsonify(results)



# ============================================================
# AI Screener APIs
# ============================================================

@app.route("/api/screener/presets")
def api_screener_presets():
    """List available preset strategies"""
    from screener import PRESETS
    presets = []
    for key, val in PRESETS.items():
        presets.append({"key": key, "name": val["name"], "desc": val["desc"]})
    return jsonify(presets)


@app.route("/api/screener/preset/<preset_key>")
def api_screener_preset(preset_key):
    """Run a preset screening strategy"""
    limit = int(request.args.get("limit", 50))
    sort_by = request.args.get("sort", "change_pct")
    from screener import run_preset
    result = run_preset(preset_key, limit=limit, sort_by=sort_by)
    # Clean up internal fields
    for s in result.get("results", []):
        s.pop("_quick_score", None)
    return jsonify(safe_json(result))


@app.route("/api/screener/query")
def api_screener_query():
    """Run a natural language screening query"""
    q = request.args.get("q", "")
    limit = int(request.args.get("limit", 50))
    sort_by = request.args.get("sort", "change_pct")
    if not q:
        return jsonify({"error": "Missing query parameter 'q'"})
    from screener import run_query
    result = run_query(q, limit=limit, sort_by=sort_by)
    for s in result.get("results", []):
        s.pop("_quick_score", None)
    return jsonify(safe_json(result))


@app.route("/api/screener/scan")
def api_screener_scan():
    """AI enhanced scan - deep analysis on top candidates"""
    top_n = int(request.args.get("top", 30))
    from screener import run_enhanced_scan
    result = run_enhanced_scan(top_n=top_n)
    return jsonify(safe_json(result))


# ============================================================
# WeCom Alert APIs
# ============================================================

@app.route("/api/alert/send", methods=["POST"])
def api_alert_send():
    """Send a message via WeCom"""
    from alert_push import send_wecom_message
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON body"})

    msg = data.get("message", "")
    msg_type = data.get("type", "text")  # text or markdown
    title = data.get("title", "")

    if not msg:
        return jsonify({"error": "Missing message"})

    try:
        if msg_type == "markdown" and title:
            result = send_wecom_message(content=msg, msg_type="markdown", title=title)
        else:
            result = send_wecom_message(content=msg, msg_type="text")
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/alert/push/screener")
def api_alert_push_screener():
    """Push screener results to WeCom"""
    from screener import run_preset, run_query
    from alert_push import send_screener_report

    mode = request.args.get("mode", "preset")
    target = request.args.get("target", "momentum")

    if mode == "preset":
        result = run_preset(target, limit=10)
    else:
        result = run_query(target, limit=10)

    if "error" in result:
        return jsonify({"error": result["error"]})

    try:
        sent = send_screener_report(result)
        return jsonify({"success": True, "sent": sent})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/alert/push/stock/<symbol>")
def api_alert_push_stock(symbol):
    """Push stock analysis report to WeCom"""
    from alert_push import send_stock_report

    try:
        sent = send_stock_report(symbol)
        return jsonify({"success": True, "sent": sent})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/alert/push/market")
def api_alert_push_market():
    """Push market overview to WeCom"""
    from alert_push import send_market_overview

    try:
        sent = send_market_overview()
        return jsonify({"success": True, "sent": sent})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500



# ============================================================
# Portfolio APIs
# ============================================================

@app.route("/api/portfolio/list")
def api_portfolio_list():
    """List all portfolios"""
    return jsonify(pm.list_portfolios())


@app.route("/api/portfolio/create", methods=["POST"])
def api_portfolio_create():
    """Create a new portfolio"""
    data = request.get_json() or {}
    name = data.get("name", "New Portfolio")
    capital = int(data.get("capital", 1000000))
    desc = data.get("description", "")
    p = pm.create_portfolio(name, capital, desc)
    return jsonify({"success": True, "id": p.id, "name": p.name})


@app.route("/api/portfolio/<portfolio_id>")
def api_portfolio_detail(portfolio_id):
    """Get portfolio detail"""
    result = pm.get_portfolio(portfolio_id)
    # Get real-time prices
    from data.price import get_latest_price
    price_data = {}
    if "positions" in result:
        codes = [p["code"] for p in result["positions"]]
        for code_str in codes:
            try:
                info = get_latest_price(code_str)
                if info:
                    price_data[code_str] = {"price": info.get("price", 0), "change_pct": info.get("change_pct", 0)}
            except:
                pass
    if result and "error" not in result:
        p_obj = pm.portfolios.get(portfolio_id)
        if p_obj:
            p_obj.update_prices(price_data)
            result = p_obj.to_dict()
            result["analysis"] = p_obj.get_analysis()
    return jsonify(safe_json(result))


@app.route("/api/portfolio/<portfolio_id>/buy", methods=["POST"])
def api_portfolio_buy(portfolio_id):
    """Buy a stock in portfolio"""
    data = request.get_json() or {}
    code = data.get("code", "")
    name = data.get("name", code)
    shares = int(data.get("shares", 100))
    price = float(data.get("price", 0))
    result = pm.buy(portfolio_id, code, name, shares, price)
    return jsonify(safe_json(result))


@app.route("/api/portfolio/<portfolio_id>/sell", methods=["POST"])
def api_portfolio_sell(portfolio_id):
    """Sell a stock from portfolio"""
    data = request.get_json() or {}
    code = data.get("code", "")
    result = pm.sell(portfolio_id, code)
    return jsonify(safe_json(result))


@app.route("/api/portfolio/<portfolio_id>/analysis")
def api_portfolio_analysis(portfolio_id):
    """Get portfolio analysis with real-time prices"""
    if portfolio_id not in pm.portfolios:
        return jsonify({"error": "Portfolio not found"})

    from data.price import get_latest_price
    p = pm.portfolios[portfolio_id]
    price_data = {}
    for pos in p.positions:
        try:
            info = get_latest_price(pos.code)
            if info:
                price_data[pos.code] = {"price": info.get("price", 0), "change_pct": info.get("change_pct", 0)}
            import time
            time.sleep(0.15)
        except:
            pass

    p.update_prices(price_data)
    analysis = p.get_analysis()
    return jsonify(analysis)


# Watchlist APIs
@app.route("/api/watchlist/list")
def api_watchlist_list():
    return jsonify(pm.list_watchlists())


@app.route("/api/watchlist/<name>")
def api_watchlist_detail(name):
    result = pm.get_watchlist(name)
    # Get real-time prices for watchlist stocks
    if "error" not in result:
        from data.price import get_latest_price
        stocks = result.get("stocks", [])
        for s in stocks:
            try:
                info = get_latest_price(s["code"])
                if info:
                    s["price"] = info.get("price", 0)
                    s["change_pct"] = info.get("change_pct", 0)
                    s["name"] = s["name"] or info.get("name", s["code"])
                import time
                time.sleep(0.15)
            except:
                pass
    return jsonify(safe_json(result))


@app.route("/api/watchlist/create", methods=["POST"])
def api_watchlist_create():
    data = request.get_json() or {}
    name = data.get("name", "default")
    desc = data.get("description", "")
    result = pm.create_watchlist(name, desc)
    return jsonify({"success": True, "name": name})


@app.route("/api/watchlist/<name>/add", methods=["POST"])
def api_watchlist_add(name):
    data = request.get_json() or {}
    code = data.get("code", "")
    stock_name = data.get("name", "")
    result = pm.add_to_watchlist(name, code, stock_name)
    return jsonify(safe_json(result))


@app.route("/api/watchlist/<name>/remove", methods=["POST"])
def api_watchlist_remove(name):
    data = request.get_json() or {}
    code = data.get("code", "")
    result = pm.remove_from_watchlist(name, code)
    return jsonify({"success": result})


@app.route("/api/backtest/<symbol>")
def api_backtest(symbol):
    """Run enhanced backtest with all strategies"""
    from data.price import get_price_data
    from backtest_enhanced import (
        compare_strategies, run_enhanced_backtest,
        STRATEGY_REGISTRY, benchmark_buy_hold, get_equity_curve
    )

    mode = request.args.get("mode", "compare")
    strategies = request.args.get("strategies", "all")
    capital = int(request.args.get("capital", 1000000))

    df = get_price_data(symbol, datalen=300)
    if df.empty:
        return jsonify({"error": "No price data"})

    if mode == "compare":
        # Compare all strategies
        result = compare_strategies(df, symbol=symbol, initial_capital=capital)
        return jsonify(safe_json(result))

    elif mode == "single":
        # Single strategy with equity curve
        strat = strategies.split(",")[0] if strategies != "all" else "ma_cross"
        bt = run_enhanced_backtest(df, strat, symbol, capital)
        if not bt:
            return jsonify({"error": "Strategy failed"})

        # Generate equity curve
        curve = get_equity_curve(df, strat, capital)

        # Benchmark
        benchmark = benchmark_buy_hold(df, capital)

        return jsonify({
            "strategy_name": bt.strategy_name,
            "total_return": round(bt.total_return, 2),
            "annualized_return": round(bt.annualized_return, 2),
            "sharpe_ratio": round(bt.sharpe_ratio, 3),
            "sortino_ratio": round(getattr(bt, "sortino_ratio", 0), 3) if isinstance(getattr(bt, "sortino_ratio", 0), float) else 0,
            "calmar_ratio": round(getattr(bt, "calmar_ratio", 0), 3) if isinstance(getattr(bt, "calmar_ratio", 0), float) else 0,
            "max_drawdown": round(bt.max_drawdown, 2),
            "win_rate": round(bt.win_rate, 2),
            "total_trades": bt.total_trades,
            "profit_factor": round(bt.profit_factor, 3),
            "max_consecutive_losses": getattr(bt, "max_consecutive_losses", 0),
            "equity_curve": curve,
            "benchmark": benchmark,
        })

    elif mode == "list":
        # Return available strategies
        strat_list = []
        for key, val in STRATEGY_REGISTRY.items():
            strat_list.append({
                "key": key,
                "name": val["name"],
                "params": val["default_params"],
            })
        return jsonify({"strategies": strat_list})

    return jsonify({"error": "Unknown mode"})


@app.route("/api/backtest/<symbol>/optimize")
def api_backtest_optimize(symbol):
    """Parameter optimization for a strategy"""
    from data.price import get_price_data
    from backtest_enhanced import optimize_strategy

    strategy = request.args.get("strategy", "ma_cross")
    metric = request.args.get("metric", "total_return")

    df = get_price_data(symbol, datalen=300)
    if df.empty:
        return jsonify({"error": "No price data"})

    # Define parameter grids
    param_grids = {
        'ma_cross': {'short_period': [3, 5, 10], 'long_period': [10, 20, 30, 60]},
        'rsi': {'rsi_period': [7, 14, 21], 'oversold': [20, 30], 'overbought': [70, 80]},
        'macd': {'fast': [8, 12], 'slow': [20, 26, 30], 'signal_period': [7, 9]},
        'bollinger': {'period': [15, 20, 25], 'std_dev': [1.5, 2.0, 2.5]},
        'momentum': {'lookback': [10, 20, 30], 'threshold': [0.02, 0.05, 0.08]},
        'mean_reversion': {'window': [15, 20, 30], 'z_threshold': [1.5, 2.0, 2.5]},
        'volume_breakout': {'volume_period': [10, 20], 'price_period': [10, 20]},
        'kdj': {},
        'ma_rsi_combined': {},
    }

    grid = param_grids.get(strategy, {'short_period': [5, 10], 'long_period': [20, 30]})

    if not grid:
        return jsonify({"error": "No optimization params for this strategy"})

    result = optimize_strategy(df, strategy, grid, symbol, metric=metric)
    return jsonify(safe_json(result))



@app.route("/api/minute/<symbol>")
def api_minute(symbol):
    """Get intraday 1-minute K-line data"""
    from data.price import get_minute_data
    df = get_minute_data(symbol, datalen=240)
    if df.empty:
        return jsonify({"error": "No minute data"})

    minute_data = []
    for _, row in df.iterrows():
        d = row.name
        if hasattr(d, "strftime"):
            ds = d.strftime("%Y-%m-%d %H:%M")
        else:
            ds = str(d)[:16]
        minute_data.append({
            "time": ds,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row.get("volume", 0)),
        })

    # Calculate average price line for 分时图
    total_amount = 0
    total_volume = 0
    for m in minute_data:
        total_amount += m["close"] * m["volume"]
        total_volume += m["volume"]

    return jsonify({
        "minute": minute_data,
        "symbol": symbol,
    })


@app.route("/api/stock/<symbol>/indicators")
def api_stock_indicators(symbol):
    """Get detailed technical indicators for chart overlay"""
    from data.price import get_price_data
    from analysis.technical import get_trend_detail

    df = get_price_data(symbol, datalen=120)
    if df.empty:
        return jsonify({"error": "No data"})

    indicators = get_trend_detail(df)

    # Build MACD, KDJ, RSI data for chart overlay
    import pandas as pd
    import numpy as np

    macd_data = []
    kdj_data = []
    rsi_data = []
    boll_data = []

    close = df['close']

    # MACD
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9).mean()
    histogram = macd_line - signal_line

    for i in range(len(df)):
        d = df.index[i]
        ds = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
        macd_data.append({
            "time": ds,
            "macd": float(macd_line.iloc[i]),
            "signal": float(signal_line.iloc[i]),
            "histogram": float(histogram.iloc[i]),
        })

    # KDJ
    low_min = df['low'].rolling(window=9).min()
    high_max = df['high'].rolling(window=9).max()
    rsv = (close - low_min) / (high_max - low_min) * 100
    rsv = rsv.fillna(50)
    k = rsv.ewm(com=2).mean()
    d_kdj = k.ewm(com=2).mean()
    j = 3 * k - 2 * d_kdj

    for i in range(len(df)):
        d = df.index[i]
        ds = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
        kdj_data.append({
            "time": ds,
            "k": float(k.iloc[i]),
            "d": float(d_kdj.iloc[i]),
            "j": float(j.iloc[i]),
        })

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, float('nan'))
    rsi = 100 - (100 / (1 + rs))

    for i in range(len(df)):
        d = df.index[i]
        ds = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
        rsi_data.append({
            "time": ds,
            "rsi": float(rsi.iloc[i]) if not pd.isna(rsi.iloc[i]) else 50,
        })

    # Bollinger Bands
    ma20 = close.rolling(window=20).mean()
    std20 = close.rolling(window=20).std()
    upper = ma20 + 2 * std20
    lower = ma20 - 2 * std20

    for i in range(len(df)):
        d = df.index[i]
        ds = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
        boll_data.append({
            "time": ds,
            "upper": float(upper.iloc[i]) if not pd.isna(upper.iloc[i]) else 0,
            "middle": float(ma20.iloc[i]) if not pd.isna(ma20.iloc[i]) else 0,
            "lower": float(lower.iloc[i]) if not pd.isna(lower.iloc[i]) else 0,
            "close": float(close.iloc[i]),
        })

    return jsonify({
        "macd": macd_data,
        "kdj": kdj_data,
        "rsi": rsi_data,
        "boll": boll_data,
        "current": indicators,
    })


# ═══════════════════════════════════════════════════════════
# NEW: Prediction + Sentiment + Chart API
# ═══════════════════════════════════════════════════════════

@app.route("/api/predict/<symbol>")
def api_predict(symbol):
    """ML + LSTM price prediction (5-day)."""
    try:
        result = predict_stock(symbol.upper(), use_llm=False)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/predict/<symbol>/llm")
def api_predict_llm(symbol):
    """ML + LSTM + DeepSeek LLM synthesis."""
    try:
        result = predict_stock(symbol.upper(), use_llm=True)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sentiment-social/<symbol>")
def api_sentiment_social(symbol):
    """Social sentiment from Guba forum + LLM analysis."""
    try:
        result = analyze_social_sentiment(symbol.upper())
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sentiment/<symbol>")
def api_sentiment(symbol):
    """News sentiment analysis."""
    try:
        result = get_sentiment_for_stock(symbol.upper())
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chart/<symbol>")
def api_chart(symbol):
    """Generate and return interactive chart HTML."""
    try:
        df = fetch_price_data(symbol.upper(), datalen=200)
        if df.empty:
            return jsonify({"error": f"No data for {symbol}"}), 404
        indicators = fetch_indicators(df)
        path = plotly_chart(df, indicators=indicators, symbol=symbol.upper(), days=120)
        if path and os.path.exists(path):
            return open(path).read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
        return jsonify({"error": "Chart generation failed"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/full-analysis/<symbol>")
def api_full_analysis(symbol):
    """Full analysis: prediction + sentiment + indicators in one call."""
    sym = symbol.upper()
    result = {"symbol": sym, "timestamp": datetime.now().isoformat()}

    # Prediction
    try:
        result["prediction"] = predict_stock(sym, use_llm=False)
    except Exception as e:
        result["prediction"] = {"error": str(e)}

    # Social sentiment (non-blocking if slow)
    try:
        result["social_sentiment"] = analyze_social_sentiment(sym)
    except Exception as e:
        result["social_sentiment"] = {"error": str(e)}

    # News sentiment
    try:
        result["news_sentiment"] = get_sentiment_for_stock(sym)
    except Exception as e:
        result["news_sentiment"] = {"error": str(e)}

    return jsonify(result)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='TradeMind Web Dashboard')
    parser.add_argument('--host', default='0.0.0.0', help='Bind address')
    parser.add_argument('--port', type=int, default=5000, help='Port number')
    args = parser.parse_args()
    print(f"TradeMind Web Dashboard starting on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)
