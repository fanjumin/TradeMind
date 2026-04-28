"""
TradeMind Global Market Data
==============================
Data sources:
- HK stocks: Tencent qt.gtimg.cn (real-time quotes, no K-line)
- Global indices: Sina hq.sinajs.cn (Dow, Nasdaq, S&P, Hang Seng)
"""

import requests
import json
import time

# ====== HONG KONG STOCKS ======
HK_STOCKS = {
    "00700": "腾讯控股",
    "09988": "阿里巴巴-W",
    "09618": "京东集团-SW",
    "01810": "小米集团-W",
    "02318": "中国平安",
    "01024": "快手-W",
    "09888": "百度集团-SW",
    "03690": "美团-W",
    "00981": "中芯国际",
    "02015": "理想汽车-W",
    "09866": "蔚来-SW",
    "09868": "小鹏汽车-W",
}


def get_hk_stocks(codes=None):
    """
    Get real-time HK stock quotes from Tencent.
    Returns list of dicts with price, change, volume etc.
    """
    if codes is None:
        codes = list(HK_STOCKS.keys())

    # Build batch query
    params = ",".join([f"r_hk{c}" for c in codes])
    url = f"http://qt.gtimg.cn/q={params}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        lines = r.text.strip().rstrip(";").split(";")

        results = []
        for line in lines:
            if "~" not in line:
                continue
            p = line.split("~")
            if len(p) < 45:
                continue

            code = p[2] if len(p) > 2 else ""
            results.append({
                "code": code,
                "name": p[1] if len(p) > 1 else "",
                "price": float(p[3]) if len(p) > 3 and p[3] else 0,
                "prev_close": float(p[4]) if len(p) > 4 and p[4] else 0,
                "open": float(p[5]) if len(p) > 5 and p[5] else 0,
                "high": float(p[33]) if len(p) > 33 and p[33] else 0,
                "low": float(p[34]) if len(p) > 34 and p[34] else 0,
                "change": float(p[31]) if len(p) > 31 and p[31] else 0,
                "change_pct": float(p[32]) if len(p) > 32 and p[32] else 0,
                "volume": float(p[36]) if len(p) > 36 and p[36] else 0,
                "amount": float(p[37]) if len(p) > 37 and p[37] else 0,
                "pe": float(p[39]) if len(p) > 39 and p[39] else 0,
                "turnover": float(p[38]) if len(p) > 38 and p[38] else 0,
                "market": "HK",
            })

        return results
    except Exception as e:
        return []


def get_hk_stock_detail(code):
    """Get detailed HK stock quote"""
    results = get_hk_stocks([code])
    return results[0] if results else None


# ====== GLOBAL INDICES ======
GLOBAL_INDICES = {
    "道琼斯": "gb_$dji",
    "纳斯达克": "gb_$ixic",
    "标普500": "gb_$inx",
    "恒生指数": "int_hangseng",
}


def get_global_indices():
    """
    Get global major indices from Sina.
    Returns dict of {name: {price, change, change_pct, time}}
    """
    codes = ",".join(GLOBAL_INDICES.values())
    url = f"https://hq.sinajs.cn/list={codes}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn/",
    }

    try:
        r = requests.get(url, headers=headers, timeout=10)
        lines = r.text.strip().split(";")
        names = list(GLOBAL_INDICES.keys())

        results = {}
        for i, line in enumerate(lines):
            if "=" not in line or """ not in line:
                continue

            data = line.split("=", 1)[1].strip().strip(";").strip(""")
            if not data:
                continue

            parts = data.split(",")
            name = names[i] if i < len(names) else f"index_{i}"

            try:
                results[name] = {
                    "name": parts[0] if len(parts) > 0 else name,
                    "price": float(parts[1]) if len(parts) > 1 and parts[1] else 0,
                    "change": float(parts[3]) if len(parts) > 3 and parts[3] else 0,
                    "change_pct": round(
                        float(parts[3]) / float(parts[1]) * 100
                        if len(parts) > 3 and parts[3] and len(parts) > 1 and float(parts[1])
                        else 0,
                        2,
                    ),
                    "time": parts[2] if len(parts) > 2 else "",
                }
            except (ValueError, ZeroDivisionError):
                results[name] = {"name": parts[0], "price": 0, "change": 0, "change_pct": 0}

        return results
    except Exception as e:
        return {}


# ====== COMBINED MARKET OVERVIEW ======
def get_market_overview():
    """
    Get combined market overview: A-share indices + HK stocks + Global indices.
    """
    # Get A-share indices from existing module
    try:
        import sys
        sys.path.insert(0, "/home/guxiao/projects/Skills Code/TradeMind")
        from data.index import get_all_indices_status
        a_indices = get_all_indices_status()
    except:
        a_indices = {}

    hk_stocks = get_hk_stocks()
    g_indices = get_global_indices()

    return {
        "a_shares": a_indices,
        "hk_stocks": hk_stocks,
        "global_indices": g_indices,
    }


if __name__ == "__main__":
    print("=== Hong Kong Stocks ===")
    hk = get_hk_stocks()
    for s in hk:
        pct_str = f"+{s['change_pct']:.2f}%" if s['change_pct'] > 0 else f"{s['change_pct']:.2f}%"
        print(f"  {s['code']} {s['name']} HK${s['price']:.2f} ({pct_str})")

    print("\n=== Global Indices ===")
    gi = get_global_indices()
    for name, info in gi.items():
        pct_str = f"+{info['change_pct']:.2f}%" if info['change_pct'] > 0 else f"{info['change_pct']:.2f}%"
        print(f"  {name}: {info['price']:.2f} ({pct_str})")

    print("\n=== Combined Overview ===")
    overview = get_market_overview()
    print(f"  A-share indices: {len(overview['a_shares'])}")
    print(f"  HK stocks: {len(overview['hk_stocks'])}")
    print(f"  Global indices: {len(overview['global_indices'])}")
