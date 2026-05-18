"""TradeMind Unified — 所有页面 + API 统一服务"""
import sys, os, json
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_from_directory

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__, template_folder="web/templates")

# =============================================
# Web Routes (from web/app.py)
# =============================================

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

# API v1 blueprint
from web.api_v1 import api_v1, OPENAPI_SPEC, SWAGGER_HTML
app.register_blueprint(api_v1)

@app.route('/api/docs')
def api_docs_global():
    return SWAGGER_HTML

@app.route('/api/openapi.json')
def api_openapi_global():
    return jsonify(OPENAPI_SPEC)

@app.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# Helper functions from web/app.py
def safe_json(obj):
    if isinstance(obj, dict):
        return {k: safe_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [safe_json(v) for v in obj]
    elif isinstance(obj, float):
        if obj == float('inf'): return 999.0
        if obj == float('-inf'): return -999.0
        if obj != obj: return 0
        return obj
    elif hasattr(obj, 'item'):
        return safe_json(obj.item())
    return obj

def safe_jsonify(obj, *args, **kwargs):
    return jsonify(safe_json(obj), *args, **kwargs)

# === Web Routes ===
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
    elif hasattr(obj, 'item'):
        return safe_json(obj.item())
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


@app.route('/api/skills/alpha-evol')
def api_alpha_evol():
    """Aggregate existing analysis and return Alpha Evol friendly JSON"""
    symbol = request.args.get('symbol', '').upper()
    if not symbol:
        return jsonify({'error': 'Missing symbol parameter'}), 400
    try:
        info = get_latest_price(symbol)
        df = get_price_data(symbol, datalen=120)

        kline = []
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                d = row.name
                ds = d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)[:10]
                kline.append({
                    'time': ds,
                    'open': float(row['open']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'close': float(row['close']),
                    'volume': float(row.get('volume', 0)),
                })

        trend = get_trend(df)
        indicators = fetch_indicators(df)

        basic = get_basic_info(symbol)
        basic_score, _ = get_basic_score(basic)

        sentiment = {}
        try:
            sentiment = get_sentiment_for_stock(symbol) or {}
        except:
            sentiment = {}

        # Compose scores (example mapping, adjust per real logic)
        ability_scores = {
            'technical': min(1, max(0, (indicators.get('momentum', 0) if isinstance(indicators, dict) else 0.5))),
            'fundamental': min(1, max(0, (basic_score / 10) if isinstance(basic_score, (int, float)) else 0.3)),
            'sentiment': min(1, max(0, (sentiment.get('score', 0) if isinstance(sentiment, dict) else 0.2))),
            'risk_control': 0.5,
            'execution': 0.4,
        }

        score = get_score(trend, 0, basic_score, indicators)
        signal = get_signal(score)

        evolution_log = [
            {'ts': datetime.utcnow().isoformat(), 'note': f'自动分析：score {round(score,2)}', 'delta': {'technical': 0.01}}
        ]

        result = {
            'level': 1,
            'exp': 12,
            'exp_next': 100,
            'ability_scores': ability_scores,
            'evolution_log': evolution_log,
            'analysis': {
                'symbol': symbol,
                'title': f"{info.get('name', symbol)} · 快速分析",
                'summary': f"信号: {signal}；趋势: {trend.get('summary','-') if isinstance(trend, dict) else trend}",
                'buy_signals': [{'type': 'signal', 'price': info.get('price', 0), 'prob': 0.6}] if info else [],
                'sell_signals': [],
            },
            'kline': kline,
        }
        return jsonify(safe_json(result))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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


@app.route('/skills/alpha-evol')
def skills_alpha_evol():
    """Serve the Alpha Evol static template for visualization."""
    try:
        path = os.path.join(os.path.dirname(__file__), 'platform', 'templates', 'skills', 'alpha-evol.html')
        if os.path.exists(path):
            return open(path, 'r', encoding='utf-8').read()
        return "Alpha Evol template not found", 404
    except Exception as e:
        return f"Error: {e}", 500


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


    return jsonify(result)


# =============================================
# API/SaaS Routes (from trademind-api)
# =============================================
import sys as _api_sys
_api_sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trademind-api"))
from api_auth import require_free
from api_key_manager import generate_key, list_keys, get_usage_stats, create_payment_order, confirm_payment
from payment import verify_notify

@app.route('/about')
def about_page():
    return render_template('about.html')

@app.route('/subscribe')
def subscribe_page():
    return render_template('subscribe.html')

@app.route('/docs')
def docs_page():
    return render_template('docs.html')

@app.route('/tutorial')
def tutorial_page():
    return render_template('tutorial.html')

@app.route('/contact')
def contact_page():
    return render_template('contact.html')

# =============================================
# API v2 — Key Management (no stock data)
# =============================================

def api_response(data=None, error=None, status=200):
    resp = {'success': error is None, 'timestamp': datetime.now().isoformat()}
    if data is not None: resp['data'] = data
    if error: resp['error'] = error
    return jsonify(resp), status

def api_error(msg, code=400):
    return api_response(error=msg, status=code)

# Generate a free API key (anyone can do this)
@app.route('/api/v2/key/generate')
@require_free
def key_generate():
    from api_key_manager import generate_key
    result = generate_key('free', 'web_user')
    return api_response(data={'key': result['key'], 'tier': result['tier']})

# =============================================
# ADMIN — API Key & Payment Management
# =============================================

@app.route('/api/admin/keys')
def admin_keys():
    from api_key_manager import list_keys, get_usage_stats
    keys = list_keys()
    stats = get_usage_stats()
    return jsonify({'keys': keys, 'stats': stats})

@app.route('/api/admin/gen_key', methods=['POST'])
def admin_gen_key():
    data = request.get_json() or {}
    tier = data.get('tier', 'free')
    name = data.get('name', '')
    days = data.get('days', 365)
    from api_key_manager import generate_key
    return jsonify(generate_key(tier, name, days))

@app.route('/api/admin/payment/create', methods=['POST'])
def admin_payment_create():
    data = request.get_json() or {}
    from api_key_manager import create_payment_order
    result = create_payment_order(
        data.get('key_id', 0),
        data.get('amount', 199),
        data.get('tier', 'premium')
    )
    return jsonify(result)

@app.route('/api/admin/payment/confirm', methods=['POST'])
def admin_payment_confirm():
    data = request.get_json() or {}
    from api_key_manager import confirm_payment
    return jsonify(confirm_payment(data.get('order_id', '')))

# WeChat Pay callback
@app.route('/api/payment/notify', methods=['POST'])
def payment_notify():
    from payment import verify_notify
    verify_notify(request.headers, request.data)
    return jsonify({'code': 'SUCCESS', 'message': 'ok'})

# =============================================
# Health check
# =============================================

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'service': 'TradeMind API', 'version': 'v0.1.0'})

# =============================================
# Static files
# =============================================

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

# =============================================
# Error handlers
# =============================================

@app.errorhandler(404)
def not_found(e):
    return api_error('Not found', 404)

@app.errorhandler(500)
def server_error(e):
    return api_error('Internal server error', 500)



# =============================================
# Backup Routes (integrated from sync_server)
# =============================================
import backup_module as bm
from flask import send_file, Response as FlaskResponse

# Start watchdog on app startup
_watchdog_started = False

@app.before_request
def start_watchdog():
    global _watchdog_started
    if not _watchdog_started:
        _watchdog_started = True
        wd = bm.Watchdog(bm.DEFAULT_DB)
        wd.start()
        import atexit
        atexit.register(wd.stop)

@app.route("/backup")
def backup_page():
    return render_template("backup.html")

@app.route("/api/backups")
def api_list_backups():
    bk = bm.BackupManager()
    return jsonify({"backups": bk.list(), "db_path": bm.DEFAULT_DB, "backup_dir": str(bm.BACKUP_DIR)})

@app.route("/api/backup", methods=["POST"])
def api_do_backup():
    bk = bm.BackupManager()
    p = bm.Path(bm.DEFAULT_DB)
    if p.exists():
        r = bk.save(p.read_bytes())
        pr = bm.push_notification(r["name"], r["size"], source="manual")
        return jsonify({"ok": True, "name": r["name"], "push": pr})
    return jsonify({"ok": False, "error": "db not found"}), 404

@app.route("/api/download/<name>")
def api_download(name):
    bk = bm.BackupManager()
    try:
        data = bk.load(name)
        resp = FlaskResponse(data, mimetype="application/octet-stream")
        resp.headers["Content-Disposition"] = f"attachment; filename={name}"
        return resp
    except FileNotFoundError:
        return jsonify({"error": "not found"}), 404

@app.route("/api/restore", methods=["POST"])
def api_restore():
    data = request.get_json() or {}
    name = data.get("name", "")
    if not name:
        return jsonify({"error": "missing name"}), 400
    bk = bm.BackupManager()
    r = bk.restore(name, bm.DEFAULT_DB)
    return jsonify({"ok": True, **r})

@app.route("/api/delete/<name>", methods=["DELETE"])
def api_delete(name):
    bk = bm.BackupManager()
    bk.delete(name)
    return jsonify({"ok": True})

@app.route("/api/upload", methods=["POST"])
def api_upload():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "no file"}), 400
    data = file.read()
    bk = bm.BackupManager()
    r = bk.save(data, file.filename)
    return jsonify({"ok": True, "name": r["name"]})

@app.route("/api/push_config")
def api_get_push_config():
    return jsonify(bm.load_push_config())

@app.route("/api/push_config", methods=["POST"])
def api_set_push_config():
    data = request.get_json() or {}
    cfg = bm.load_push_config()
    if "enabled" in data: cfg["enabled"] = bool(data["enabled"])
    if "wecom_user" in data: cfg["wecom_user"] = str(data["wecom_user"])
    bm.save_push_config(cfg)
    return jsonify({"ok": True, **cfg})

@app.route("/api/push_test", methods=["POST"])
def api_push_test():
    r = bm.push_notification("test-message.txt", 0, source="测试")
    return jsonify(r)

@app.route("/api/backup_ping")
def api_backup_ping():
    return jsonify({"ok": True, "time": datetime.now().isoformat()})


# =============================================
# Update Routes (version management)
# =============================================
import update_manager as um

@app.route("/update")
def update_page():
    return render_template("update.html")

@app.route("/api/update/check")
def api_update_check():
    return jsonify(um.check_update())

@app.route("/api/update/download")
def api_update_download():
    data = um.download_source()
    if isinstance(data, dict) and "error" in data:
        return jsonify(data), 500
    from flask import Response as FlaskResp
    resp = FlaskResp(data, mimetype="application/zip")
    resp.headers["Content-Disposition"] = "attachment; filename=TradeMind-source.zip"
    return resp

@app.route("/api/update/apply", methods=["POST"])
def api_update_apply():
    return jsonify(um.apply_update())

@app.route("/api/update/rollback", methods=["POST"])
def api_update_rollback():
    data = request.get_json() or {}
    return jsonify(um.rollback(data.get("version", "")))

@app.route("/api/update/versions")
def api_update_versions():
    return jsonify({"versions": um.list_versions()})

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TradeMind Unified Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    print(f"  TradeMind Unified Server")
    print(f"  Pages: / /analyze /strategies /trade /about /subscribe /docs /tutorial /contact")
    print(f"  API:   /api/indices /api/stock/<s> /api/screener/* /api/alert/send /api/v2/* /api/admin/*")
    print(f"  http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)
