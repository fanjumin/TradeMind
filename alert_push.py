"""
TradeMind WeCom Alert Push System
===================================
Sends formatted stock alerts, screener reports, and market overviews
to WeCom (企业微信) via the Flask proxy on easykai.cn:8081.
"""

import requests
import json
import time
from datetime import datetime


WECOM_PROXY_URL = "http://easykai.cn:8081/send"
WECOM_USER = "FanJuMin"
WECOM_AGENT_ID = "1000004"


def send_wecom_message(content, msg_type="text", title=""):
    if msg_type == "markdown":
        payload = {
            "user": WECOM_USER,
            "agent_id": WECOM_AGENT_ID,
            "msgtype": "markdown",
            "markdown": {"title": title or "TradeMind", "content": content},
        }
    else:
        payload = {
            "user": WECOM_USER,
            "agent_id": WECOM_AGENT_ID,
            "msgtype": "text",
            "text": {"content": content},
        }

    try:
        r = requests.post(WECOM_PROXY_URL, json=payload, timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def send_screener_report(screener_result):
    preset_name = screener_result.get("preset", screener_result.get("query", "Scan"))
    total_found = screener_result.get("total_found", 0)
    results = screener_result.get("results", [])

    lines = ["## TradeMind AI选股 - " + preset_name, ""]
    lines.append("> 共找到 " + str(total_found) + " 只股票 | " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    lines.append("")

    for i, s in enumerate(results[:10]):
        code = s.get("code", "")
        name = s.get("name", "")
        price = s.get("price", 0)
        pct = s.get("change_pct", 0)
        pe = s.get("pe", 0)
        pb = s.get("pb", 0)
        mc = s.get("market_cap", 0) / 1e4
        turnover = s.get("turnover", 0)

        pct_str = ("+" if pct > 0 else "") + "%.2f" % pct + "%"
        mc_str = "%.0f亿" % mc if mc > 0 else "--"

        if pct > 0:
            emoji = "\U0001f4c8"
        elif pct < 0:
            emoji = "\U0001f4c9"
        else:
            emoji = "\U0001f504"

        lines.append("**" + str(i+1) + ". " + name + " (" + code + ")** ¥" + "%.2f" % price + " " + pct_str)
        lines.append("   PE: %.1f | PB: %.2f | 市值: %s | 换手: %.1f%%" % (pe, pb, mc_str, turnover))
        lines.append("")

    if results:
        lines.append("---")
        lines.append("*数据来源: TradeMind AI | Sina Finance*")

    content = "\n".join(lines)
    title = "AI选股 - " + preset_name

    return send_wecom_message(content, msg_type="markdown", title=title)


def send_stock_report(symbol):
    from data.price import get_latest_price, get_price_data
    from analysis.technical import get_trend, get_trend_detail
    from analysis.scoring import get_score, get_signal, get_signal_cn
    from data.fund import get_fund_flow

    info = get_latest_price(symbol)
    if not info:
        return send_wecom_message("股票 " + symbol + " 未找到")

    name = info.get("name", symbol)
    price = info.get("price", 0)
    pct = info.get("change_pct", 0)
    pct_str = ("+" if pct > 0 else "") + "%.2f" % pct + "%"

    df = get_price_data(symbol, datalen=60)
    trend = get_trend(df)
    indicators = get_trend_detail(df)
    fund_total, _ = get_fund_flow(symbol)
    score = get_score(trend, fund_total, 50, indicators)
    signal = get_signal_cn(score)

    trend_emojis = {"uptrend": "\U0001f4c8", "strong_uptrend": "\U0001f680", "downtrend": "\U0001f4c9", "neutral": "\U0001f504"}
    trend_emoji = trend_emojis.get(trend, "\U0001f504")

    lines = [
        "## " + trend_emoji + " " + name + " (" + symbol + ")",
        "",
        "> 现价: ¥%.2f (%s) | %s" % (price, pct_str, datetime.now().strftime("%H:%M")),
        "",
        "### 技术指标",
        "",
        "- **趋势**: " + trend + " | **信号**: " + signal,
        "- **评分**: %d/100" % score,
        "- **RSI**: %.1f" % indicators.get("rsi", 0),
        "- **MACD**: %.4f" % indicators.get("macd", 0),
        "- **MA5**: %.2f" % indicators.get("ma5", 0),
        "- **MA20**: %.2f" % indicators.get("ma20", 0),
        "- **MA60**: %.2f" % indicators.get("ma60", 0),
        "",
        "### 资金流向",
        "",
        "- **5日主力净流入**: %.0f" % fund_total,
        "",
        "---",
        "*TradeMind AI 实时分析*",
    ]

    content = "\n".join(lines)
    return send_wecom_message(content, msg_type="markdown", title="个股分析: " + name)


def send_market_overview():
    from data.index import get_all_indices_status

    indices = get_all_indices_status()

    lines = ["## TradeMind 市场概览", "", "> " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ""]

    for name, info in indices.items():
        pct = info.get("change_pct", 0)
        close = info.get("close", 0)
        pct_str = ("+" if pct > 0 else "") + "%.2f" % pct + "%"
        if pct > 0:
            emoji = "\U0001f4c8"
        elif pct < 0:
            emoji = "\U0001f4c9"
        else:
            emoji = "\U0001f504"
        lines.append("- " + emoji + " **" + name + "**: %.2f (%s)" % (close, pct_str))

    lines.append("")
    lines.append("---")
    lines.append("*TradeMind AI | 实时行情*")

    content = "\n".join(lines)
    return send_wecom_message(content, msg_type="markdown", title="市场概览")


def send_alert_message(symbol, alert_type, details):
    emoji_map = {
        "price_above": "\U0001f53c",
        "price_below": "\U0001f53d",
        "rsi_oversold": "\U0001f4b0",
        "rsi_overbought": "\u26a0\ufe0f",
        "volume_surge": "\U0001f4ca",
    }
    emoji = emoji_map.get(alert_type, "\U0001f514")
    content = emoji + " **预警: " + symbol + "**\n\n" + details
    return send_wecom_message(content, msg_type="markdown", title="交易预警")


if __name__ == "__main__":
    import sys
    print("TradeMind WeCom Alert Push System")
    print()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "test":
            result = send_wecom_message("TradeMind WeCom 推送测试 - " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            print("Test result:", json.dumps(result, ensure_ascii=False))
        elif cmd == "market":
            result = send_market_overview()
            print("Market overview sent:", json.dumps(result, ensure_ascii=False))
        elif cmd == "stock":
            symbol = sys.argv[2] if len(sys.argv) > 2 else "600519"
            result = send_stock_report(symbol)
            print("Stock report sent for %s:" % symbol, json.dumps(result, ensure_ascii=False))
        elif cmd == "screener":
            preset = sys.argv[2] if len(sys.argv) > 2 else "momentum"
            from screener import run_preset
            result = run_preset(preset, limit=10)
            push_result = send_screener_report(result)
            print("Screener report sent for %s:" % preset, json.dumps(push_result, ensure_ascii=False))
    else:
        print("Usage:")
        print("  python alert_push.py test          - Send test message")
        print("  python alert_push.py market        - Push market overview")
        print("  python alert_push.py stock <code>  - Push stock report")
        print("  python alert_push.py screener <preset> - Push screener results")
