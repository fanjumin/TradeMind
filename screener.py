"""
TradeMind AI Smart Stock Screener
==================================
Fetches all A-share stocks from Sina, applies multi-condition filters,
and returns ranked results with technical analysis.

Features:
- Full market scan (5500+ stocks) with caching
- Multi-condition filtering (price, PE, PB, market cap, turnover, change%, trend, score)
- Natural language query support (Chinese)
- Preset screening strategies
"""

import requests
import json
import time
import re
from datetime import datetime

# Global cache for stock list
_stock_cache = None
_cache_time = None
_CACHE_TTL = 300  # 5 minutes

# Sina stock list API
_SINA_LIST_URL = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"


def fetch_all_stocks(force_refresh=False):
    global _stock_cache, _cache_time
    if not force_refresh and _stock_cache and _cache_time:
        if time.time() - _cache_time < _CACHE_TTL:
            return _stock_cache

    headers = {"User-Agent": "Mozilla/5.0"}
    all_stocks = []
    page = 1
    while True:
        try:
            r = requests.get(
                _SINA_LIST_URL,
                params={"page": str(page), "num": "80", "node": "hs_a", "_s_r_a": "page"},
                headers=headers, timeout=10
            )
            data = json.loads(r.text)
            if not data:
                break
            all_stocks.extend(data)
            page += 1
            time.sleep(0.1)
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break

    stocks = []
    for s in all_stocks:
        try:
            stocks.append({
                "code": s.get("code", ""),
                "symbol": s.get("symbol", ""),
                "name": s.get("name", ""),
                "price": float(s.get("trade", 0) or 0),
                "change": float(s.get("pricechange", 0) or 0),
                "change_pct": float(s.get("changepercent", 0) or 0),
                "open": float(s.get("open", 0) or 0),
                "high": float(s.get("high", 0) or 0),
                "low": float(s.get("low", 0) or 0),
                "volume": float(s.get("volume", 0) or 0),
                "amount": float(s.get("amount", 0) or 0),
                "pe": float(s.get("per", 0) or 0),
                "pb": float(s.get("pb", 0) or 0),
                "market_cap": float(s.get("mktcap", 0) or 0),
                "nmc": float(s.get("nmc", 0) or 0),
                "turnover": float(s.get("turnoverratio", 0) or 0),
                "buy": float(s.get("buy", 0) or 0),
                "sell": float(s.get("sell", 0) or 0),
            })
        except (ValueError, TypeError):
            continue

    _stock_cache = stocks
    _cache_time = time.time()
    return stocks


class StockFilter:
    def __init__(self):
        self.conditions = []

    def add(self, field, op, value):
        self.conditions.append({"field": field, "op": op, "value": value})
        return self

    def price_above(self, v): return self.add("price", ">=", v)
    def price_below(self, v): return self.add("price", "<=", v)
    def price_between(self, lo, hi): return self.add("price", "between", (lo, hi))
    def pe_below(self, v): return self.add("pe", "<=", v)
    def pe_above(self, v): return self.add("pe", ">=", v)
    def pe_between(self, lo, hi): return self.add("pe", "between", (lo, hi))
    def pb_below(self, v): return self.add("pb", "<=", v)
    def pb_above(self, v): return self.add("pb", ">=", v)
    def market_cap_above(self, v): return self.add("market_cap", ">=", v)
    def market_cap_below(self, v): return self.add("market_cap", "<=", v)
    def turnover_above(self, v): return self.add("turnover", ">=", v)
    def turnover_below(self, v): return self.add("turnover", "<=", v)
    def change_pct_above(self, v): return self.add("change_pct", ">=", v)
    def change_pct_below(self, v): return self.add("change_pct", "<=", v)
    def name_contains(self, v): return self.add("name", "contains", v)

    def apply(self, stocks):
        results = []
        for s in stocks:
            if all(self._check(s, c) for c in self.conditions):
                results.append(s)
        return results

    def _check(self, stock, condition):
        field = condition["field"]
        op = condition["op"]
        value = condition["value"]
        if field not in stock:
            return False
        v = stock[field]
        if field == "name" and op == "contains":
            return value in v
        if op == ">": return v > value
        if op == ">=": return v >= value
        if op == "<": return v < value
        if op == "<=": return v <= value
        if op == "==": return v == value
        if op == "!=": return v != value
        if op == "between": return value[0] <= v <= value[1]
        if op == "in": return v in value
        return False


def parse_query(query):
    f = StockFilter()
    q = query.lower()

    def extract_number(text, start=0):
        match = re.search(r"([\d.]+)\s*(亿|万|%)?", text[start:])
        if match:
            num = float(match.group(1))
            unit = match.group(2)
            if unit == "亿": num *= 1e4
            return num, start + match.end()
        return None, start

    # PE
    for pat in ["pe小于", "pe低于", "市盈率小于", "市盈率低于", "pe<", "市盈率<"]:
        idx = q.find(pat)
        if idx >= 0:
            num, _ = extract_number(q, idx + len(pat))
            if num: f.pe_below(num)
    for pat in ["pe大于", "pe高于", "市盈率大于", "市盈率高于", "pe>", "市盈率>"]:
        idx = q.find(pat)
        if idx >= 0:
            num, _ = extract_number(q, idx + len(pat))
            if num: f.pe_above(num)

    # PB
    for pat in ["pb小于", "pb低于", "市净率小于", "市净率低于", "pb<", "市净率<"]:
        idx = q.find(pat)
        if idx >= 0:
            num, _ = extract_number(q, idx + len(pat))
            if num: f.pb_below(num)
    for pat in ["pb大于", "pb高于", "市净率大于", "市净率高于", "pb>", "市净率>"]:
        idx = q.find(pat)
        if idx >= 0:
            num, _ = extract_number(q, idx + len(pat))
            if num: f.pb_above(num)

    # Market cap
    for pat in ["市值大于", "市值超过", "市值>"]:
        idx = q.find(pat)
        if idx >= 0:
            num, _ = extract_number(q, idx + len(pat))
            if num: f.market_cap_above(num)
    for pat in ["市值小于", "市值低于", "市值<"]:
        idx = q.find(pat)
        if idx >= 0:
            num, _ = extract_number(q, idx + len(pat))
            if num: f.market_cap_below(num)

    # Price
    for pat in ["价格大于", "股价大于", "价格高于", "股价高于", "价格>", "股价>"]:
        idx = q.find(pat)
        if idx >= 0:
            num, _ = extract_number(q, idx + len(pat))
            if num: f.price_above(num)
    for pat in ["价格小于", "股价小于", "价格低于", "股价低于", "价格<", "股价<"]:
        idx = q.find(pat)
        if idx >= 0:
            num, _ = extract_number(q, idx + len(pat))
            if num: f.price_below(num)
    for pat in ["价格在", "股价在"]:
        idx = q.find(pat)
        if idx >= 0:
            lo, _ = extract_number(q, idx + len(pat))
            if lo:
                rest = q[idx + len(pat):]
                hi_match = re.search(r"到\s*([\d.]+)", rest)
                if hi_match: f.price_between(lo, float(hi_match.group(1)))

    # Change
    for pat in ["涨幅大于", "涨幅>", "涨超"]:
        idx = q.find(pat)
        if idx >= 0:
            num, _ = extract_number(q, idx + len(pat))
            if num: f.change_pct_above(num)
    for pat in ["跌幅大于", "跌幅>", "跌超"]:
        idx = q.find(pat)
        if idx >= 0:
            num, _ = extract_number(q, idx + len(pat))
            if num: f.change_pct_below(-num)

    # Turnover
    for pat in ["换手率大于", "换手率>", "换手大于"]:
        idx = q.find(pat)
        if idx >= 0:
            num, _ = extract_number(q, idx + len(pat))
            if num: f.turnover_above(num)
    for pat in ["换手率小于", "换手率<", "换手小于"]:
        idx = q.find(pat)
        if idx >= 0:
            num, _ = extract_number(q, idx + len(pat))
            if num: f.turnover_below(num)

    # Keywords
    if "低价股" in q or "低价" in q: f.price_below(10)
    if "高价股" in q or "高价" in q: f.price_above(100)
    if "涨停" in q: f.change_pct_above(9.5)
    if "跌停" in q: f.change_pct_below(-9.5)
    if "超跌" in q: f.change_pct_below(-5)
    if "大盘股" in q: f.market_cap_above(1000 * 1e4)
    if "小盘股" in q or "小盘" in q: f.market_cap_below(50 * 1e4)
    if "高股息" in q or "高分红" in q: f.pe_below(15); f.pb_below(2)
    if "高成长" in q or "成长股" in q: f.change_pct_above(3)

    # Industry keywords
    industries = ["消费", "科技", "医疗", "医药", "新能源", "半导体", "芯片", "人工",
                  "电池", "光伏", "风电", "汽车", "金融", "银行", "保险", "地产",
                  "军工", "航天", "航空", "食品", "白酒", "家电", "物流", "快递",
                  "化工", "钢铁", "煤炭", "电力", "通信", "互联网", "游戏", "教育",
                  "旅游", "传媒", "环保", "农业", "养殖"]
    for ind in industries:
        if ind in q: f.name_contains(ind); break

    # Dedup
    seen = set()
    unique = []
    for c in f.conditions:
        key = (c["field"], c["op"], str(c["value"]))
        if key not in seen:
            seen.add(key)
            unique.append(c)
    f.conditions = unique
    return f


PRESETS = {
    "low_pe": {"name": "低估值", "desc": "PE<20, PB<3, 价格>5", "filter": lambda: StockFilter().pe_below(20).pb_below(3).price_above(5)},
    "oversold": {"name": "超跌反弹", "desc": "跌幅>5%, PE>0, 换手率>3%", "filter": lambda: StockFilter().change_pct_below(-5).pe_above(0).turnover_above(3)},
    "momentum": {"name": "强势突破", "desc": "涨幅>3%, 换手率>5%, 市值>50亿", "filter": lambda: StockFilter().change_pct_above(3).turnover_above(5).market_cap_above(50*1e4)},
    "blue_chip": {"name": "白马龙头", "desc": "市值>500亿, PE 10-50, PB<10, 价格>20", "filter": lambda: StockFilter().market_cap_above(500*1e4).pe_between(10,50).pb_below(10).price_above(20)},
    "small_cap": {"name": "小盘成长", "desc": "市值<100亿, PE<40, 涨幅>0", "filter": lambda: StockFilter().market_cap_below(100*1e4).pe_below(40).change_pct_above(0)},
    "high_turnover": {"name": "高换手活跃股", "desc": "换手率>10%, 价格>5", "filter": lambda: StockFilter().turnover_above(10).price_above(5)},
    "limit_up": {"name": "涨停板", "desc": "涨幅>=9.5%", "filter": lambda: StockFilter().change_pct_above(9.5)},
    "limit_down": {"name": "跌停板", "desc": "跌幅<=-9.5%", "filter": lambda: StockFilter().change_pct_below(-9.5)},
}


def run_preset(preset_key, stocks=None, limit=50, sort_by="change_pct"):
    if preset_key not in PRESETS:
        return {"error": f"Unknown preset: {preset_key}", "available": list(PRESETS.keys())}
    if stocks is None:
        stocks = fetch_all_stocks()
    preset = PRESETS[preset_key]
    f = preset["filter"]()
    results = f.apply(stocks)
    if results and sort_by in results[0]:
        results.sort(key=lambda x: x.get(sort_by, 0), reverse=True)
    return {"preset": preset["name"], "desc": preset["desc"], "total_found": len(results), "results": results[:limit]}


def run_query(query, stocks=None, limit=50, sort_by="change_pct", sort_desc=True):
    if stocks is None:
        stocks = fetch_all_stocks()
    f = parse_query(query)
    results = f.apply(stocks)
    if results and sort_by in results[0]:
        results.sort(key=lambda x: x.get(sort_by, 0), reverse=sort_desc)
    return {"query": query, "conditions": f.conditions, "total_found": len(results), "results": results[:limit]}


def run_enhanced_scan(stocks=None, top_n=30, min_score=60):
    from data.price import get_price_data, get_latest_price
    from analysis.technical import get_trend, get_trend_detail
    from analysis.scoring import get_score, get_signal, get_signal_cn
    from data.fund import get_fund_flow

    if stocks is None:
        stocks = fetch_all_stocks()

    candidates = [s for s in stocks if s["price"] > 0 and s["amount"] > 1000 and "ST" not in s["name"] and s["pe"] != 0]

    def quick_score(s):
        score = 50
        if 2 < s["change_pct"] < 8: score += 10
        elif s["change_pct"] >= 8: score += 5
        if 0 < s["pe"] < 30: score += 10
        elif s["pe"] < 0: score -= 10
        if 3 < s["turnover"] < 15: score += 5
        if 50*1e4 < s["market_cap"] < 1000*1e4: score += 5
        return score

    for s in candidates:
        s["_quick_score"] = quick_score(s)

    candidates.sort(key=lambda x: x.get("_quick_score", 0), reverse=True)
    top = candidates[:top_n]
    results = []

    for s in top:
        try:
            code = s["code"]
            df = get_price_data(code, datalen=60)
            if df.empty: continue
            trend = get_trend(df)
            indicators = get_trend_detail(df)
            fund_total, _ = get_fund_flow(code)
            score = get_score(trend, fund_total, 50, indicators)
            s["trend"] = trend
            s["score"] = score
            s["signal"] = get_signal_cn(score)
            s["rsi"] = indicators.get("rsi", 50)
            s["macd"] = indicators.get("macd", 0)
            s["fund_net"] = round(float(fund_total), 0)
            results.append(s)
            time.sleep(0.2)
        except:
            continue

    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "total_scanned": len(candidates), "analyzed": len(results), "results": results}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python screener.py --preset <name> | --query '<q>' | --scan [top_n]")
        print("Presets:", ", ".join(PRESETS.keys()))
        sys.exit(0)

    mode = sys.argv[1]
    if mode == "--preset":
        key = sys.argv[2] if len(sys.argv) > 2 else "low_pe"
        result = run_preset(key)
        print(f"=== {result['preset']} ({result['desc']}) ===")
        print(f"Found: {result['total_found']} stocks")
        for i, s in enumerate(result["results"][:20]):
            print(f"  {i+1}. {s['code']} {s['name']} {s['price']:.2f} ({s['change_pct']:+.2f}%) PE={s['pe']:.1f} PB={s['pb']:.2f} MC={s['market_cap']/1e4:.0f}亿")
    elif mode == "--query":
        q = sys.argv[2] if len(sys.argv) > 2 else "PE小于20"
        result = run_query(q)
        print(f"=== Query: {result['query']} ===")
        print(f"Found: {result['total_found']} stocks")
        for i, s in enumerate(result["results"][:20]):
            print(f"  {i+1}. {s['code']} {s['name']} {s['price']:.2f} ({s['change_pct']:+.2f}%) PE={s['pe']:.1f}")
    elif mode == "--scan":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        result = run_enhanced_scan(top_n=n)
        print(f"=== AI Enhanced Scan ===")
        print(f"Scanned: {result['total_scanned']}, Analyzed: {result['analyzed']}")
        for i, s in enumerate(result["results"][:20]):
            print(f"  {i+1}. {s['code']} {s['name']} {s['price']:.2f} ({s['change_pct']:+.2f}%) Score={s['score']} Trend={s['trend']}")
