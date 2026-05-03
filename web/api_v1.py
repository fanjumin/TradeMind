"""
TradeMind REST API v1 — 对标 OpenBB/Kavout 的标准化 API 层
提供: API Key 认证 / 版本路由 / OpenAPI 文档 / 统一错误格式
"""
import sys, os, json, time, hashlib, secrets, functools
from datetime import datetime
from functools import wraps
from flask import Blueprint, request, jsonify, current_app, render_template_string
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))
from strategy_market import list_strategies, get_strategy, compare_strategies, benchmark_strategies, rank_strategies, categories_summary, export_strategy

api_v1 = Blueprint('api_v1', __name__, url_prefix='/api/v1')

# ============================================================
# Auth
# ============================================================

API_KEYS = {}  # Loaded from api_config.json

def load_api_keys():
    """Load API keys from config."""
    global API_KEYS
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'api_config.json')
    try:
        with open(config_path) as f:
            cfg = json.load(f)
        API_KEYS = cfg.get('api_keys', {})
        if not API_KEYS:
            # Auto-generate a default key
            default_key = 'tm-' + secrets.token_hex(16)
            API_KEYS['default'] = default_key
            cfg['api_keys'] = API_KEYS
            with open(config_path, 'w') as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            print(f"[API] Generated default API key: {default_key}")
    except Exception as e:
        print(f"[API] Warning: Could not load api_keys: {e}")
        API_KEYS = {'default': 'tm-default-dev-key'}

load_api_keys()

def require_api_key(f):
    """Decorator: require X-API-Key header or ?api_key= query param."""
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if not key:
            return jsonify({"error": "Missing API key", "hint": "Use X-API-Key header or ?api_key= query param"}), 401
        if key not in API_KEYS.values():
            return jsonify({"error": "Invalid API key"}), 403
        return f(*args, **kwargs)
    return decorated

# ============================================================
# Helpers
# ============================================================

def safe_json(obj):
    """Replace inf/nan/numpy types with safe JSON values."""
    if isinstance(obj, dict):
        return {k: safe_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [safe_json(v) for v in obj]
    elif isinstance(obj, float):
        if obj == float('inf'): return 999.0
        if obj == float('-inf'): return -999.0
        if obj != obj: return 0
        return obj
    elif isinstance(obj, bool):
        return bool(obj)
    elif hasattr(obj, 'item'):  # numpy types
        return safe_json(obj.item())
    return obj

def api_response(data=None, error=None, status=200):
    """Standard API response envelope."""
    body = {"success": error is None, "timestamp": datetime.now().isoformat()}
    if data is not None:
        body["data"] = safe_json(data)
    if error:
        body["error"] = error
    return jsonify(body), status

def get_symbol(symbol):
    """Normalize stock symbol."""
    return symbol.upper().strip()

# ============================================================
# Meta endpoints
# ============================================================

@api_v1.route('/')
def api_root():
    """API root — list available endpoints."""
    return api_response(data={
        "name": "TradeMind API v1",
        "version": "0.1.0",
        "docs": "/api/docs",
        "openapi": "/api/openapi.json",
        "endpoints": {
            "market": ["GET /market/indices", "GET /market/sectors"],
            "stocks": ["GET /stock/<symbol>", "GET /stock/<symbol>/technical", 
                       "GET /stock/<symbol>/fundamental", "GET /stock/<symbol>/sentiment",
                       "GET /stock/<symbol>/prediction", "GET /stock/<symbol>/financials",
                       "GET /stock/<symbol>/full"],
            "screener": ["GET /screener/presets", "GET /screener/run/<preset>", "GET /screener/query"],
            "factors": ["GET /factors/list", "GET /factors/ic", "GET /factors/backtest/<factor>", "GET /factors/correlation"],
            "backtest": ["GET /backtest/<symbol>", "POST /backtest/custom"],
            "alerts": ["GET /alerts", "POST /alerts", "DELETE /alerts/<id>", "GET /alerts/check/<symbol>"],
            "portfolio": ["GET /portfolio/list", "POST /portfolio/create", "GET /portfolio/<id>"],
            "system": ["GET /health", "GET /stats"]
        }
    })

@api_v1.route('/health')
def api_health():
    """Health check — no auth required."""
    return api_response(data={"status": "ok", "version": "0.1.0"})

@api_v1.route('/stats')
@require_api_key
def api_stats():
    """API usage stats."""
    return api_response(data={
        "api_keys": len(API_KEYS),
        "endpoints": 20,
    })

# ============================================================
# Market endpoints
# ============================================================

@api_v1.route('/market/indices')
@require_api_key
def market_indices():
    """Get all A-share market index status (上证/深证/创业板/科创50)."""
    from data.index import get_all_indices_status
    try:
        data = get_all_indices_status()
        return api_response(data=data)
    except Exception as e:
        return api_response(error=str(e), status=500)

@api_v1.route('/market/sectors')
@require_api_key
def market_sectors():
    """Get sector/industry performance overview."""
    from data.sector import get_sector_data
    try:
        data = get_sector_data()
        return api_response(data=data)
    except Exception as e:
        return api_response(error=str(e), status=500)

# ============================================================
# Stock endpoints
# ============================================================

@api_v1.route('/stock/<symbol>')
@require_api_key
def stock_detail(symbol):
    """Get real-time quote + basic info for a stock."""
    sym = get_symbol(symbol)
    from data.price import get_latest_price
    from data.basic import get_basic_info, get_basic_score
    try:
        info = get_latest_price(sym)
        if not info or "error" in info:
            return api_response(error=f"Stock {sym} not found", status=404)
        basic = get_basic_info(sym)
        basic_score, basic_reasons = get_basic_score(basic)
        return api_response(data={
            "symbol": sym,
            "quote": info,
            "fundamentals": basic,
            "fundamental_score": basic_score,
            "fundamental_reasons": basic_reasons,
        })
    except Exception as e:
        return api_response(error=str(e), status=500)

@api_v1.route('/stock/<symbol>/technical')
@require_api_key
def stock_technical(symbol):
    """Get full technical analysis (82 indicators + trend + patterns)."""
    sym = get_symbol(symbol)
    from data.price import get_price_data
    from analysis.technical import get_trend, get_trend_detail, detect_candlestick_patterns, detect_price_anomaly
    try:
        df = get_price_data(sym, datalen=200)
        if df.empty:
            return api_response(error=f"No price data for {sym}", status=404)
        trend = get_trend(df)
        indicators = get_trend_detail(df)
        patterns = detect_candlestick_patterns(df)
        anomalies = detect_price_anomaly(df)
        return api_response(data={
            "symbol": sym,
            "data_points": len(df),
            "trend": trend,
            "indicators": safe_json(indicators),
            "candlestick_patterns": patterns,
            "anomalies": anomalies,
        })
    except Exception as e:
        return api_response(error=str(e), status=500)

@api_v1.route('/stock/<symbol>/fundamental')
@require_api_key
def stock_fundamental(symbol):
    """Get fundamental analysis (valuation, scoring)."""
    sym = get_symbol(symbol)
    from data.basic import get_basic_info, get_basic_score
    from data.valuation import get_valuation
    try:
        basic = get_basic_info(sym)
        basic_score, reasons = get_basic_score(basic)
        valuation = get_valuation(sym)
        return api_response(data={
            "symbol": sym,
            "basic": basic,
            "score": basic_score,
            "reasons": reasons,
            "valuation": safe_json(valuation),
        })
    except Exception as e:
        return api_response(error=str(e), status=500)

@api_v1.route('/stock/<symbol>/sentiment')
@require_api_key
def stock_sentiment(symbol):
    """Get sentiment analysis (news + social)."""
    sym = get_symbol(symbol)
    from analysis.sentiment import get_sentiment_for_stock
    from analysis.social_sentiment import analyze_social_sentiment
    try:
        news_s = get_sentiment_for_stock(sym)
        social_s = analyze_social_sentiment(sym)
        return api_response(data={
            "symbol": sym,
            "news_sentiment": safe_json(news_s),
            "social_sentiment": safe_json(social_s),
        })
    except Exception as e:
        return api_response(error=str(e), status=500)

@api_v1.route('/stock/<symbol>/prediction')
@require_api_key
def stock_prediction(symbol):
    """Get ML/AI price prediction (5-day)."""
    sym = get_symbol(symbol)
    from analysis.predict import predict_stock
    try:
        result = predict_stock(sym, use_llm=False)
        return api_response(data=safe_json(result))
    except Exception as e:
        return api_response(error=str(e), status=500)

@api_v1.route('/stock/<symbol>/full')
@require_api_key
def stock_full(symbol):
    """Full comprehensive analysis: quote + technical + fundamental + sentiment + prediction."""
    sym = get_symbol(symbol)
    from data.price import get_latest_price, get_price_data
    from data.basic import get_basic_info, get_basic_score
    from analysis.technical import get_trend, get_trend_detail, detect_candlestick_patterns
    from analysis.sentiment import get_sentiment_for_stock
    from analysis.social_sentiment import analyze_social_sentiment
    from analysis.predict import predict_stock
    try:
        result = {"symbol": sym, "timestamp": datetime.now().isoformat()}
        
        # Quote
        info = get_latest_price(sym)
        if not info or "error" in info:
            return api_response(error=f"Stock {sym} not found", status=404)
        result["quote"] = info
        
        # Technical
        df = get_price_data(sym, datalen=200)
        if not df.empty:
            result["trend"] = get_trend(df)
            result["indicators"] = safe_json(get_trend_detail(df))
            result["patterns"] = detect_candlestick_patterns(df)
        
        # Fundamental
        basic = get_basic_info(sym)
        score, reasons = get_basic_score(basic)
        result["fundamentals"] = basic
        result["fundamental_score"] = score
        result["fundamental_reasons"] = reasons
        
        # Sentiment (non-blocking, return partial on error)
        try:
            result["news_sentiment"] = safe_json(get_sentiment_for_stock(sym))
        except:
            result["news_sentiment"] = {"error": "unavailable"}
        try:
            result["social_sentiment"] = safe_json(analyze_social_sentiment(sym))
        except:
            result["social_sentiment"] = {"error": "unavailable"}
        
        # Prediction
        try:
            result["prediction"] = safe_json(predict_stock(sym, use_llm=False))
        except:
            result["prediction"] = {"error": "unavailable"}
        
        return api_response(data=result)
    except Exception as e:
        return api_response(error=str(e), status=500)


# ============================================================
# Financial endpoints (v1.0 — baostock 三表分析)
# ============================================================

@api_v1.route('/stock/<symbol>/financials')
@require_api_key
def stock_financials(symbol):
    """Get comprehensive financial analysis (profit + balance + cashflow + growth)."""
    sym = get_symbol(symbol)
    from analysis.financials import analyze_financials
    try:
        result = analyze_financials(sym, years=3)
        return api_response(data=safe_json(result))
    except Exception as e:
        return api_response(error=str(e), status=500)

@api_v1.route('/stock/<symbol>/financials/report')
@require_api_key
def stock_financials_report(symbol):
    """Get formatted financial report as text."""
    sym = get_symbol(symbol)
    import io, sys
    from analysis.financials import print_financial_report
    try:
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        print_financial_report(sym)
        report = sys.stdout.getvalue()
        sys.stdout = old_stdout
        return api_response(data={"symbol": sym, "report": report})
    except Exception as e:
        return api_response(error=str(e), status=500)


# ============================================================
# Factor Analysis endpoints (v1.0 — IC/分层回测/相关性)
# ============================================================

@api_v1.route('/factors/list')
@require_api_key
def factors_list():
    """List all available factors."""
    from analysis.factors import FACTOR_DEFS
    return api_response(data={
        fname: {'name': info['name'], 'category': info['category'], 'direction': info['direction']}
        for fname, info in FACTOR_DEFS.items()
    })

@api_v1.route('/factors/ic')
@require_api_key
def factors_ic():
    """Run IC analysis on specified stock universe."""
    symbols = request.args.get('symbols', '600519,000858,000001,600036,601318,600276,000333,002594,300750,600900')
    forward_days = int(request.args.get('days', 20))
    universe = [s.strip() for s in symbols.split(',') if s.strip()]
    from analysis.factors import compute_all_factor_ics
    try:
        results = compute_all_factor_ics(universe, forward_days)
        return api_response(data=safe_json(results))
    except Exception as e:
        return api_response(error=str(e), status=500)

@api_v1.route('/factors/backtest/<factor_name>')
@require_api_key
def factors_backtest(factor_name):
    """Run stratified backtest for a single factor."""
    symbols = request.args.get('symbols', '600519,000858,000001,600036,601318,600276,000333,002594,300750,600900')
    n_groups = int(request.args.get('groups', 5))
    universe = [s.strip() for s in symbols.split(',') if s.strip()]
    from analysis.factors import stratified_backtest
    try:
        result = stratified_backtest(factor_name, universe, n_groups)
        return api_response(data=safe_json(result))
    except Exception as e:
        return api_response(error=str(e), status=500)

@api_v1.route('/factors/correlation')
@require_api_key
def factors_correlation():
    """Compute factor correlation matrix."""
    symbols = request.args.get('symbols', '600519,000858,000001,600036,601318,600276,000333,002594,300750,600900')
    universe = [s.strip() for s in symbols.split(',') if s.strip()]
    from analysis.factors import compute_factor_correlation
    try:
        result = compute_factor_correlation(universe)
        return api_response(data=safe_json(result))
    except Exception as e:
        return api_response(error=str(e), status=500)

# ============================================================
# ============================================================
# Screener endpoints
# Screener endpoints
# ============================================================

@api_v1.route('/screener/presets')
@require_api_key
def screener_presets():
    """List all preset screening strategies."""
    from screener import PRESETS
    presets = [{"key": k, "name": v["name"], "desc": v["desc"]} for k, v in PRESETS.items()]
    return api_response(data=presets)

@api_v1.route('/screener/run/<preset>')
@require_api_key
def screener_run(preset):
    """Run a preset screener."""
    from screener import run_preset
    limit = int(request.args.get('limit', 30))
    sort = request.args.get('sort', 'change_pct')
    try:
        result = run_preset(preset, limit=limit, sort_by=sort)
        for s in result.get("results", []):
            s.pop("_quick_score", None)
        return api_response(data=safe_json(result))
    except Exception as e:
        return api_response(error=str(e), status=500)

@api_v1.route('/screener/query')
@require_api_key
def screener_query():
    """Natural language stock screening."""
    from screener import run_query
    q = request.args.get('q', '')
    limit = int(request.args.get('limit', 30))
    if not q:
        return api_response(error="Missing 'q' parameter", status=400)
    try:
        result = run_query(q, limit=limit)
        for s in result.get("results", []):
            s.pop("_quick_score", None)
        return api_response(data=safe_json(result))
    except Exception as e:
        return api_response(error=str(e), status=500)

# ============================================================
# Backtest endpoints
# ============================================================

@api_v1.route('/backtest/<symbol>')
@require_api_key
def backtest_symbol(symbol):
    """Run backtest for a stock with specified strategy."""
    sym = get_symbol(symbol)
    strategy = request.args.get('strategy', 'macd')
    days = int(request.args.get('days', 365))
    from data.price import get_price_data
    from backtest import run_backtest, format_backtest_result
    try:
        df = get_price_data(sym, datalen=days+50)
        if df.empty:
            return api_response(error=f"No price data for {sym}", status=404)
        result = run_backtest(df, strategy_name=strategy, symbol=sym)
        summary = {
            "symbol": sym,
            "strategy": strategy,
            "total_return_pct": round(result.total_return * 100, 2),
            "sharpe": round(result.sharpe_ratio, 2) if result.sharpe_ratio else 0,
            "max_drawdown_pct": round(result.max_drawdown * 100, 2),
            "win_rate_pct": round(result.win_rate * 100, 1),
            "total_trades": result.total_trades,
            "annual_return_pct": round(result.annualized_return * 100, 2) if result.annualized_return else 0,
            "sortino": round(result.sortino_ratio, 2) if result.sortino_ratio else 0,
            "calmar": round(result.calmar_ratio, 2) if result.calmar_ratio else 0,
            "profit_factor": round(result.profit_factor, 2) if result.profit_factor else 0,
        }
        return api_response(data=safe_json(summary))
    except Exception as e:
        return api_response(error=str(e), status=500)

@api_v1.route('/backtest/custom', methods=['POST'])
@require_api_key
def backtest_custom():
    """Run custom backtest with parameters."""
    data = request.get_json() or {}
    symbol = get_symbol(data.get('symbol', ''))
    strategy = data.get('strategy', 'macd')
    days = int(data.get('days', 365))
    capital = int(data.get('capital', 1000000))
    if not symbol:
        return api_response(error="Missing 'symbol'", status=400)
    from data.price import get_price_data
    from backtest import run_backtest, format_backtest_result
    try:
        df = get_price_data(symbol, datalen=days+50)
        if df.empty:
            return api_response(error=f"No price data for {symbol}", status=404)
        result = run_backtest(df, strategy_name=strategy, symbol=symbol, initial_capital=capital)
        summary = {
            "symbol": symbol,
            "strategy": strategy,
            "total_return_pct": round(result.total_return * 100, 2),
            "sharpe": round(result.sharpe_ratio, 2) if result.sharpe_ratio else 0,
            "max_drawdown_pct": round(result.max_drawdown * 100, 2),
            "win_rate_pct": round(result.win_rate * 100, 1),
            "total_trades": result.total_trades,
            "sortino": round(result.sortino_ratio, 2) if result.sortino_ratio else 0,
            "profit_factor": round(result.profit_factor, 2) if result.profit_factor else 0,
        }
        return api_response(data=safe_json(summary))
    except Exception as e:
        return api_response(error=str(e), status=500)

# ============================================================
# Alert endpoints
# ============================================================

@api_v1.route('/alerts')
@require_api_key
def alerts_list():
    """List all configured alerts."""
    from alerts import AlertEngine
    engine = AlertEngine()
    alerts = engine.list_alerts()
    return api_response(data={"count": len(alerts), "alerts": alerts})

@api_v1.route('/alerts', methods=['POST'])
@require_api_key
def alerts_create():
    """Create a new alert."""
    data = request.get_json() or {}
    symbol = get_symbol(data.get('symbol', ''))
    alert_type = data.get('type', '')
    threshold = float(data.get('threshold', 0))
    message = data.get('message', '')
    if not symbol or not alert_type:
        return api_response(error="Missing 'symbol' or 'type'", status=400)
    from alerts import AlertEngine, AlertConfig
    try:
        engine = AlertEngine()
        config = AlertConfig(
            alert_type=alert_type,
            threshold=threshold,
            symbol=symbol,
            message=message or f"{symbol} {alert_type} alert triggered"
        )
        engine.add_alert(config)
        return api_response(data={"symbol": symbol, "type": alert_type, "threshold": threshold, "status": "created"})
    except Exception as e:
        return api_response(error=str(e), status=500)

@api_v1.route('/alerts/<int:alert_id>', methods=['DELETE'])
@require_api_key
def alerts_delete(alert_id):
    """Remove an alert."""
    from alerts import AlertEngine
    try:
        engine = AlertEngine()
        engine.remove_alert(alert_id)
        return api_response(data={"removed": alert_id})
    except Exception as e:
        return api_response(error=str(e), status=500)

@api_v1.route('/alerts/check/<symbol>')
@require_api_key
def alerts_check(symbol):
    """Check all alerts for a stock."""
    sym = get_symbol(symbol)
    from data.price import get_price_data, get_latest_price
    from analysis.technical import get_trend_detail
    from alerts import AlertEngine, check_stock_alerts, generate_alert_report
    try:
        df = get_price_data(sym, datalen=200)
        if df.empty:
            return api_response(error=f"No price data for {sym}", status=404)
        engine = AlertEngine()
        triggered = check_stock_alerts(sym, df, engine=engine)
        # Get price and indicators for report
        quote = get_latest_price(sym)
        price = quote.get('price', 0) if quote else 0
        indicators = get_trend_detail(df)
        report = generate_alert_report(sym, price, indicators, triggered.get('triggered', []))
        return api_response(data={"symbol": sym, "triggered": safe_json(triggered), "report": report})
    except Exception as e:
        return api_response(error=str(e), status=500)

# ============================================================
# Portfolio endpoints (lightweight, full version in app.py)
# ============================================================

@api_v1.route('/portfolio/list')
@require_api_key
def portfolio_list():
    """List all portfolios."""
    from portfolio import PortfolioManager
    pm = PortfolioManager()
    return api_response(data=pm.list_portfolios())

@api_v1.route('/portfolio/<portfolio_id>')
@require_api_key
def portfolio_detail(portfolio_id):
    """Get portfolio detail with real-time prices."""
    from portfolio import PortfolioManager
    from data.price import get_latest_price
    pm = PortfolioManager()
    result = pm.get_portfolio(portfolio_id)
    if "error" in result:
        return api_response(error=result["error"], status=404)
    # Refresh prices
    price_data = {}
    for p in result.get("positions", []):
        try:
            info = get_latest_price(p["code"])
            if info:
                price_data[p["code"]] = {"price": info.get("price", 0), "change_pct": info.get("change_pct", 0)}
        except:
            pass
    p_obj = pm.portfolios.get(portfolio_id)
    if p_obj:
        p_obj.update_prices(price_data)
        result = p_obj.to_dict()
        result["analysis"] = p_obj.get_analysis()
    return api_response(data=safe_json(result))

# ============================================================
# Simulated Trading (v2.5 Phase 2)
# ============================================================

@api_v1.route('/trade/init', methods=['POST'])
@require_api_key
def api_trade_init():
    data = request.get_json() or {}
    capital = data.get('capital', 1000000)
    from sim_trade import OrderManager
    om = OrderManager(initial_capital=capital)
    om.cash = capital
    om.positions = {}
    om.orders = {}
    om.trades = []
    om.snapshots = []
    om._save_state()
    return api_response(data={'initial_capital': capital, 'message': 'Account initialized'})


@api_v1.route('/trade/order', methods=['POST'])
@require_api_key
def api_trade_order():
    data = request.get_json() or {}
    symbol = data.get('symbol', '')
    side = data.get('side', 'buy')
    qty = int(data.get('quantity', 100))
    order_type = data.get('order_type', 'market')
    limit_price = float(data.get('limit_price', 0))
    
    from sim_trade import OrderManager, OrderSide, OrderType
    om = OrderManager()
    s = OrderSide.BUY if side == 'buy' else OrderSide.SELL
    ot = OrderType.MARKET if order_type == 'market' else OrderType.LIMIT
    
    result = om.submit_order(symbol, symbol, s, ot, qty, limit_price)
    if result.get('error'):
        return api_error(result['error'], 400)
    om.tick([symbol])
    return api_response(data=safe_json({
        'order': result['order'],
        'performance': om.get_performance(),
    }))


@api_v1.route('/trade/positions')
@require_api_key
def api_trade_positions():
    from sim_trade import OrderManager
    om = OrderManager()
    return api_response(data=safe_json(om.get_positions()))


@api_v1.route('/trade/orders')
@require_api_key
def api_trade_orders():
    from sim_trade import OrderManager
    om = OrderManager()
    status = request.args.get('status')
    from sim_trade import OrderStatus
    s = OrderStatus(status) if status else None
    return api_response(data=safe_json(om.get_orders(s)))


@api_v1.route('/trade/orders/<order_id>', methods=['DELETE'])
@require_api_key
def api_trade_cancel(order_id):
    from sim_trade import OrderManager
    om = OrderManager()
    result = om.cancel_order(order_id)
    if result.get('error'):
        return api_error(result['error'], 400)
    return api_response(data=safe_json(result))


@api_v1.route('/trade/history')
@require_api_key
def api_trade_history():
    from sim_trade import OrderManager
    om = OrderManager()
    limit = request.args.get('limit', 50, type=int)
    return api_response(data=safe_json(om.get_trades(limit)))


@api_v1.route('/trade/performance')
@require_api_key
def api_trade_performance():
    from sim_trade import OrderManager
    om = OrderManager()
    return api_response(data=safe_json(om.get_performance()))


@api_v1.route('/trade/tick', methods=['POST'])
@require_api_key
def api_trade_tick():
    from sim_trade import OrderManager
    om = OrderManager()
    r = om.tick()
    return api_response(data=safe_json(r))


@api_v1.route('/trade/reset', methods=['POST'])
@require_api_key
def api_trade_reset():
    from sim_trade import OrderManager
    om = OrderManager()
    om.cash = om.initial_capital
    om.positions = {}
    om.orders = {}
    om.trades = []
    om.snapshots = []
    om._save_state()
    return api_response(data={'message': 'Account reset', 'initial_capital': om.initial_capital})


# ============================================================
# Multi-Asset: ETF & Convertible Bonds (v2.5 Phase 2)
# ============================================================

@api_v1.route('/etf/list')
@require_api_key
def api_etf_list():
    from data.etf import fetch_etf_list
    etfs = fetch_etf_list()
    return api_response(data={'count': len(etfs), 'etfs': safe_json(etfs[:500])})


@api_v1.route('/etf/<symbol>')
@require_api_key
def api_etf_detail(symbol):
    from data.etf import get_etf_price
    p = get_etf_price(symbol)
    if p is None:
        return api_error("ETF not found", 404)
    return api_response(data=safe_json(p))


@api_v1.route('/etf/search')
@require_api_key
def api_etf_search():
    from data.etf import search_etfs
    q = request.args.get('q', '')
    results = search_etfs(q, limit=20)
    return api_response(data=safe_json({'query': q, 'count': len(results), 'results': results}))


@api_v1.route('/cb/list')
@require_api_key
def api_cb_list():
    from data.convertible import fetch_cb_list
    cbs = fetch_cb_list()
    return api_response(data={'count': len(cbs), 'cbs': safe_json(cbs)})


@api_v1.route('/cb/<symbol>')
@require_api_key
def api_cb_detail(symbol):
    from data.convertible import get_cb_price
    p = get_cb_price(symbol)
    if p is None:
        return api_error("CB not found", 404)
    return api_response(data=safe_json(p))


@api_v1.route('/cb/search')
@require_api_key
def api_cb_search():
    from data.convertible import search_cb
    q = request.args.get('q', '')
    results = search_cb(q, limit=20)
    return api_response(data=safe_json({'query': q, 'count': len(results), 'results': results}))


# ============================================================
# Strategy Marketplace (v2.5 Phase 2)
# ============================================================

@api_v1.route('/strategies')
@require_api_key
def api_strategies_list():
    """List all strategies with metadata."""
    strategies = list_strategies()
    return api_response(data={'count': len(strategies), 'strategies': safe_json(strategies)})


@api_v1.route('/strategies/<name>')
@require_api_key
def api_strategy_detail(name):
    """Get single strategy details."""
    s = get_strategy(name)
    if s is None:
        return api_error(f"Strategy '{name}' not found", 404)
    return api_response(data=safe_json(s))


@api_v1.route('/strategies/compare/<symbol>')
@require_api_key
def api_strategies_compare(symbol):
    """Compare all strategies on a symbol."""
    days = request.args.get('days', 252, type=int)
    result = compare_strategies(symbol, days=days)
    return api_response(data=safe_json(result))


@api_v1.route('/strategies/benchmark')
@require_api_key
def api_strategies_benchmark():
    """Benchmark all strategies across multiple symbols."""
    symbols_str = request.args.get('symbols', '000001,600519,000858,300750')
    symbols = [s.strip() for s in symbols_str.split(',') if s.strip()]
    days = request.args.get('days', 252, type=int)
    result = benchmark_strategies(symbols=symbols, days=days)
    return api_response(data=safe_json(result))


@api_v1.route('/strategies/rank')
@require_api_key
def api_strategies_rank():
    """Rank strategies by metric."""
    metric = request.args.get('metric', 'sharpe_ratio')
    result = rank_strategies(metric=metric)
    return api_response(data=safe_json(result))


@api_v1.route('/strategies/categories')
@require_api_key
def api_strategies_categories():
    """Get strategy category summary."""
    result = categories_summary()
    return api_response(data=safe_json(result))


@api_v1.route('/strategies/export/<name>')
@require_api_key
def api_strategies_export(name):
    """Export strategy configuration as JSON."""
    result = export_strategy(name)
    if 'error' in result:
        return api_error(result['error'], 404)
    return api_response(data=safe_json(result))


# ============================================================
# OpenAPI documentation
# ============================================================

OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "TradeMind REST API",
        "version": "0.1.0",
        "description": "A股AI分析平台 REST API — 对标 OpenBB Terminal. "
                       "提供实时行情/技术分析/基本面/情绪分析/ML预测/回测/选股/告警等全功能接口。",
        "contact": {"name": "TradeMind"}
    },
    "servers": [{"url": "http://127.0.0.1:5000/api/v1", "description": "本地服务器"}],
    "security": [{"ApiKeyAuth": []}],
    "components": {
        "securitySchemes": {
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "在 api_config.json 中配置的 API Key"
            }
        }
    },
    "paths": {
        "/health": {"get": {"summary": "健康检查", "security": [], "responses": {"200": {"description": "OK"}}}},
        "/market/indices": {"get": {"summary": "A股指数全貌", "responses": {"200": {"description": "所有主要指数状态"}}}},
        "/market/sectors": {"get": {"summary": "行业板块表现", "responses": {"200": {"description": "行业数据"}}}},
        "/stock/{symbol}": {
            "get": {"summary": "个股实时行情+基本面", "parameters": [{"name": "symbol", "in": "path", "required": True, "schema": {"type": "string"}, "example": "600519"}], "responses": {"200": {"description": "个股数据"}}}
        },
        "/stock/{symbol}/technical": {"get": {"summary": "技术分析(82指标+形态+异常)", "parameters": [{"name": "symbol", "in": "path", "required": True, "schema": {"type": "string"}}]}},
        "/stock/{symbol}/fundamental": {"get": {"summary": "基本面分析(估值+评分)", "parameters": [{"name": "symbol", "in": "path", "required": True, "schema": {"type": "string"}}]}},
        "/stock/{symbol}/sentiment": {"get": {"summary": "情绪分析(新闻+股吧社交)", "parameters": [{"name": "symbol", "in": "path", "required": True, "schema": {"type": "string"}}]}},
        "/stock/{symbol}/prediction": {"get": {"summary": "ML预测(5日方向+目标价)", "parameters": [{"name": "symbol", "in": "path", "required": True, "schema": {"type": "string"}}]}},
        "/stock/{symbol}/full": {"get": {"summary": "综合分析(全维度一站式)", "parameters": [{"name": "symbol", "in": "path", "required": True, "schema": {"type": "string"}}]}},
        "/screener/presets": {"get": {"summary": "选股预设策略列表"}},
        "/screener/run/{preset}": {"get": {"summary": "运行预设选股策略", "parameters": [{"name": "preset", "in": "path", "required": True, "schema": {"type": "string"}}]}},
        "/screener/query": {"get": {"summary": "自然语言选股", "parameters": [{"name": "q", "in": "query", "required": True, "schema": {"type": "string"}}]}},
        "/backtest/{symbol}": {"get": {"summary": "策略回测", "parameters": [{"name": "symbol", "in": "path", "required": True, "schema": {"type": "string"}}, {"name": "strategy", "in": "query", "schema": {"type": "string"}}]}},
        "/backtest/custom": {"post": {"summary": "自定义回测"}},
        "/alerts": {"get": {"summary": "告警列表"}, "post": {"summary": "创建告警"}},
        "/alerts/check/{symbol}": {"get": {"summary": "检查个股告警", "parameters": [{"name": "symbol", "in": "path", "required": True, "schema": {"type": "string"}}]}},
        "/portfolio/list": {"get": {"summary": "投资组合列表"}},
        "/etf/list": {"get": {"summary": "ETF列表"}}, "/etf/{symbol}": {"get": {"summary": "ETF实时行情"}}, "/etf/search": {"get": {"summary": "搜索ETF"}}, "/cb/list": {"get": {"summary": "可转债列表(活跃)"}}, "/cb/{symbol}": {"get": {"summary": "可转债实时行情"}}, "/cb/search": {"get": {"summary": "搜索可转债"}}, "/strategies": {"get": {"summary": "策略市场 - 策略列表及元数据"}},
        "/strategies/{name}": {"get": {"summary": "策略市场 - 单策略详情", "parameters": [{"name": "name", "in": "path", "required": True, "schema": {"type": "string"}}]}},
        "/strategies/compare/{symbol}": {"get": {"summary": "策略市场 - 单标的策略比较", "parameters": [{"name": "symbol", "in": "path", "required": True, "schema": {"type": "string"}}, {"name": "days", "in": "query", "schema": {"type": "integer", "default": 252}}]}},
        "/strategies/benchmark": {"get": {"summary": "策略市场 - 多标的基准测试", "parameters": [{"name": "symbols", "in": "query", "schema": {"type": "string"}}, {"name": "days", "in": "query", "schema": {"type": "integer", "default": 252}}]}},
        "/strategies/rank": {"get": {"summary": "策略市场 - 按指标排名", "parameters": [{"name": "metric", "in": "query", "schema": {"type": "string", "default": "sharpe_ratio"}}]}},
        "/strategies/categories": {"get": {"summary": "策略市场 - 类别概览"}},
        "/strategies/export/{name}": {"get": {"summary": "策略市场 - 导出策略配置", "parameters": [{"name": "name", "in": "path", "required": True, "schema": {"type": "string"}}]}},
        "/portfolio/{portfolio_id}": {"get": {"summary": "组合详情", "parameters": [{"name": "portfolio_id", "in": "path", "required": True, "schema": {"type": "string"}}]}},
    }
}

SWAGGER_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>TradeMind API v1 — Swagger UI</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
    <style>html{box-sizing:border-box;overflow:-moz-scrollbars-vertical;overflow-y:scroll}*,*:before,*:after{box-sizing:inherit}body{margin:0;background:#fafafa}.topbar{display:none}</style>
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
SwaggerUIBundle({
    url: "/api/openapi.json",
    dom_id: "#swagger-ui",
    presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
    layout: "BaseLayout",
    defaultModelsExpandDepth: -1,
})
</script>
</body>
</html>"""

@api_v1.route('/docs')
def api_docs():
    """Swagger UI documentation page."""
    return SWAGGER_HTML

@api_v1.route('/openapi.json')
def api_openapi():
    """OpenAPI 3.0 specification JSON."""
    return jsonify(OPENAPI_SPEC)
