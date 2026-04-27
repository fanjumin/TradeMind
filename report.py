import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.price import get_price_data, get_latest_price
from data.fund import get_fund_flow
from data.basic import get_basic_info, get_basic_score
from data.industry import get_industry_comparison
from data.valuation import get_valuation
from data.index import get_all_indices_status
from data.sector import get_top_sectors
from analysis.technical import get_trend, get_trend_detail
from analysis.scoring import get_score, get_signal, get_signal_cn


def _pad(label, value, width=42):
    return '  {:<12s}{:>30s}'.format(label, value)


def generate_report(symbol):
    lines = []
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    lines.append('=' * 60)
    lines.append('  TradeMind - A-Stock Analysis Report')
    lines.append('  Time: ' + now)
    lines.append('  Stock: ' + symbol)
    lines.append('=' * 60)

    # Real-time price
    try:
        info = get_latest_price(symbol)
        if info:
            lines.append('')
            lines.append('--- Real-Time Quote ---')
            lines.append(_pad('Name', info.get('name', '')))
            lines.append(_pad('Price', '%.2f' % info['price']))
            lines.append(_pad('Change', '%+.2f (%+.2f%%)' % (info['change'], info['change_pct'])))
            lines.append(_pad('High', '%.2f' % info['high']))
            lines.append(_pad('Low', '%.2f' % info['low']))
            lines.append(_pad('Open', '%.2f' % info['open']))
            lines.append(_pad('Volume', '%.0f' % info['volume']))
    except Exception as e:
        lines.append('  [Real-time error: %s]' % str(e))

    # K-line trend + technical indicators
    try:
        df = get_price_data(symbol)
        detail = get_trend_detail(df)
        trend = detail.get('trend', 'neutral')

        lines.append('')
        lines.append('--- Technical Analysis ---')

        lines.append('  [Moving Averages]')
        lines.append(_pad('Close', '%.2f' % detail['close']))
        lines.append(_pad('MA5', '%.2f' % detail['ma5']))
        lines.append(_pad('MA10', '%.2f' % detail['ma10']))
        lines.append(_pad('MA20', '%.2f' % detail['ma20']))
        lines.append(_pad('MA60', '%.2f' % detail['ma60']))

        close = detail['close']
        ma5 = detail.get('ma5', 0)
        ma20 = detail.get('ma20', 0)
        ma60 = detail.get('ma60', 0)
        if ma5 > 0 and ma20 > 0 and ma60 > 0:
            if close > ma5 > ma20 > ma60:
                align = 'Bullish (price>MA5>MA20>MA60)'
            elif close < ma5 < ma20 < ma60:
                align = 'Bearish (price<MA5<MA20<MA60)'
            else:
                align = 'Mixed'
            lines.append(_pad('Alignment', align))

        lines.append('')
        lines.append('  [RSI]')
        lines.append(_pad('RSI(14)', '%.2f (%s)' % (detail.get('rsi', 0), detail.get('rsi_signal', ''))))

        lines.append('')
        lines.append('  [KDJ]')
        lines.append(_pad('K', '%.2f' % detail.get('k', 0)))
        lines.append(_pad('D', '%.2f' % detail.get('d', 0)))
        lines.append(_pad('J', '%.2f (%s)' % (detail.get('j', 0), detail.get('kdj_signal', ''))))

        lines.append('')
        lines.append('  [Bollinger Bands]')
        lines.append(_pad('Upper', '%.2f' % detail.get('boll_upper', 0)))
        lines.append(_pad('Mid', '%.2f' % detail.get('boll_mid', 0)))
        lines.append(_pad('Lower', '%.2f' % detail.get('boll_lower', 0)))
        lines.append(_pad('%%B', '%.3f (%s)' % (detail.get('boll_pct_b', 0), detail.get('boll_position', ''))))
        lines.append(_pad('Width', '%.2f%%' % detail.get('boll_width', 0)))

        lines.append('')
        lines.append('  [MACD]')
        lines.append(_pad('MACD', '%.2f' % detail.get('macd', 0)))

        lines.append('')
        lines.append('  [Support/Resistance]')
        lines.append(_pad('Resistance', '%.2f (+%.2f%%)' % (detail.get('resistance', 0), detail.get('dist_to_res_pct', 0))))
        lines.append(_pad('Pivot', '%.2f' % detail.get('pivot', 0)))
        lines.append(_pad('Support', '%.2f (-%.2f%%)' % (detail.get('support', 0), detail.get('dist_to_sup_pct', 0))))

        lines.append('')
        lines.append('  [Volume-Price]')
        lines.append(_pad('Vol MA5/20', '%.0f / %.0f (ratio %.2f)' % (
            detail.get('vol_ma5', 0), detail.get('vol_ma20', 0), detail.get('vol_ratio', 0))))
        lines.append(_pad('Vol Trend', detail.get('vol_trend', '')))
        lines.append(_pad('Signal', detail.get('vol_price_signal', '')))

        lines.append('')
        lines.append(_pad('Overall Trend', trend.upper()))

    except Exception as e:
        lines.append('  [K-line error: %s]' % str(e))
        trend = 'neutral'
        detail = {}

    # Capital Flow
    try:
        fund_total, fund_detail = get_fund_flow(symbol)
        lines.append('')
        lines.append('--- Capital Flow (EastMoney) ---')

        main_today = fund_detail.get('main_force_today', 0)
        main_5d = fund_detail.get('main_force_5d_sum', 0)
        super_lg = fund_detail.get('super_large', 0)
        large = fund_detail.get('large', 0)
        medium = fund_detail.get('medium', 0)
        small = fund_detail.get('small', 0)
        main_pct = fund_detail.get('main_force_pct', 0)

        def flow_str(val):
            if val > 0: return '+%.2fM' % (val / 1e6)
            else: return '%.2fM' % (val / 1e6)

        lines.append(_pad('Today Main', '%s (%.1f%%)' % (flow_str(main_today), main_pct)))
        lines.append(_pad('  Super Lg', flow_str(super_lg)))
        lines.append(_pad('  Large', flow_str(large)))
        lines.append(_pad('  Medium', flow_str(medium)))
        lines.append(_pad('  Small', flow_str(small)))
        lines.append(_pad('5-Day Main', flow_str(main_5d)))

        daily = fund_detail.get('daily_flows', [])
        if daily:
            lines.append('')
            lines.append('  [Daily Trend]')
            for d in daily[:5]:
                lines.append('    %s  %+8.1fM  %+.1f%%' % (
                    d['date'], d['main_force'] / 1e6, d.get('change_pct', 0)))

        lines.append(_pad('Volume', '%.0f' % fund_detail.get('volume', 0)))
        lines.append(_pad('Amount', '%.0f' % fund_detail.get('amount', 0)))
    except Exception as e:
        lines.append('  [Flow error: %s]' % str(e))
        fund_total = 0

    # Fundamentals
    try:
        basic = get_basic_info(symbol)
        basic_score, basic_reasons = get_basic_score(basic)
        lines.append('')
        lines.append('--- Fundamentals ---')
        lines.append(_pad('Company', basic.get('company', 'N/A')))
        pe = basic.get('pe_ttm', 0)
        pb = basic.get('pb', 0)
        if pe > 0: lines.append(_pad('PE (TTM)', '%.2f' % pe))
        if pb > 0: lines.append(_pad('PB', '%.2f' % pb))
        eps = basic.get('eps_ttm', 0)
        if eps > 0: lines.append(_pad('EPS (TTM)', '%.2f' % eps))
        roe = basic.get('roe', 0)
        if roe > 0: lines.append(_pad('ROE', '%.1f%%' % (roe * 100)))
        npm = basic.get('np_margin', 0)
        if npm > 0: lines.append(_pad('Net Margin', '%.1f%%' % (npm * 100)))
        gpm = basic.get('gp_margin', 0)
        if gpm > 0: lines.append(_pad('Gross Marg', '%.1f%%' % (gpm * 100)))
        rev = basic.get('revenue', 0)
        if rev > 0: lines.append(_pad('Revenue', '%.1fB' % (rev / 1e8)))
        np = basic.get('net_profit', 0)
        if np > 0: lines.append(_pad('Net Profit', '%.1fB' % (np / 1e8)))
        yoy_ni = basic.get('yoy_net_income', 0)
        if yoy_ni != 0: lines.append(_pad('YOY NetIn', '%+.1f%%' % (yoy_ni * 100)))
        yoy_eps = basic.get('yoy_eps', 0)
        if yoy_eps != 0: lines.append(_pad('YOY EPS', '%+.1f%%' % (yoy_eps * 100)))
        lines.append(_pad('Score', '%d/100' % basic_score))
        for r in basic_reasons:
            lines.append('    - ' + r)
    except Exception as e:
        lines.append('  [Fundamental error: %s]' % str(e))
        basic_score = 0

    # Industry Comparison
    try:
        ind = get_industry_comparison(symbol)
        if ind and ind['industry']:
            lines.append('')
            lines.append('--- Industry Comparison ---')
            lines.append(_pad('Industry', ind['industry']))
            lines.append(_pad('Peers', str(ind['peer_count'])))

            pe_val = ind.get('pe', 0)
            pb_val = ind.get('pb', 0)
            pe_pct = ind.get('pe_percentile', 0)
            pb_pct = ind.get('pb_percentile', 0)
            pe_med = ind.get('pe_median', 0)
            pb_med = ind.get('pb_median', 0)

            pe_eval = "偏低" if pe_pct < 30 else ("合理" if pe_pct < 70 else "偏高")
            pb_eval = "偏低" if pb_pct < 30 else ("合理" if pb_pct < 70 else "偏高")

            lines.append(_pad('PE', '%.1f (%s, 行业中值%.1f)' % (pe_val, pe_eval, pe_med)))
            lines.append(_pad('PE Percentile', '%.1f%% (低于%.0f%%同行)' % (pe_pct, 100 - pe_pct)))
            lines.append(_pad('PB', '%.2f (%s)' % (pb_val, pb_eval)))
            lines.append(_pad('PB Percentile', '%.1f%%' % pb_pct))

            top = ind.get('top_peers', [])
            if top:
                lines.append('')
                lines.append('  [Cheapest Peers by PE]')
                for p in top:
                    lines.append('    %-8s PE=%-6.1f PB=%.2f' % (p['name'], p['pe'], p['pb']))
    except Exception as e:
        lines.append('  [Industry error: %s]' % str(e))

    # Valuation Models
    try:
        val = get_valuation(symbol)
        if val:
            lines.append('')
            lines.append('--- Valuation ---')

            peg = val.get('peg')
            if peg is not None:
                peg_eval = "低估" if peg < 1 else ("合理" if peg < 2 else "高估")
                lines.append(_pad('PEG', '%.2f (%s)' % (peg, peg_eval)))
            else:
                gr = val.get('growth_rate', 0)
                if gr < 0:
                    lines.append(_pad('PEG', 'N/A (负增长%+.1f%%)' % (gr * 100)))
                else:
                    lines.append(_pad('PEG', 'N/A (增长率%.1f%%)' % (gr * 100)))

            dcf = val.get('dcf_value')
            if dcf:
                dcf_rec_map = {
                    'undervalued': '低估',
                    'fair_value': '合理',
                    'slightly_overvalued': '略高估',
                    'overvalued': '高估',
                }
                rec_cn = dcf_rec_map.get(val.get('dcf_rec', ''), '')
                upside = val.get('dcf_upside', 0)
                lines.append(_pad('DCF', '%.2f (%+.1f%%, %s)' % (dcf, upside, rec_cn)))
            else:
                lines.append(_pad('DCF', 'N/A (需正增长假设)'))

            # Multi-quarter history
            hist = val.get('history', [])
            if hist:
                lines.append('')
                lines.append('  [Financial History]')
                lines.append('  %-8s %8s %8s %10s' % ('Period', 'ROE', 'NPM', 'NetProfit'))
                for h in hist[:4]:
                    qs = h.get('quarters', {})
                    for q_name in ['Q4', 'Q3', 'Q2', 'Q1']:
                        if q_name in qs:
                            q = qs[q_name]
                            np_val = q.get('net_profit', 0) / 1e8 if q.get('net_profit', 0) > 0 else 0
                            lines.append('  %-8s %7.1f%% %7.1f%% %8.0f亿' % (
                                h.get('year'), q.get('roe', 0) * 100,
                                q.get('npm', 0) * 100, np_val))
                            break  # Only show Q4 (annual)
    except Exception as e:
        lines.append('  [Valuation error: %s]' % str(e))

    # Sentiment (News Analysis)
    try:
        from data.news import get_stock_news
        from analysis.sentiment import analyze_news

        news_items = get_stock_news(symbol, max_items=20)
        sentiment = analyze_news(news_items)

        lines.append('')
        lines.append('--- Sentiment (舆情分析) ---')
        overall_s = sentiment.get('overall_score', 0)
        label_s = sentiment.get('overall_label', 'neutral')
        emoji_s = {'bullish': '🟢', 'neutral': '🟡', 'bearish': '🔴'}.get(label_s, '⚪')
        label_cn = {'bullish': '看多', 'neutral': '中性', 'bearish': '看空'}.get(label_s, '未知')
        lines.append(_pad('Overall', '%s %.2f (%s)' % (emoji_s, overall_s, label_cn)))
        lines.append(_pad('Articles', '%d (bullish:%d neutral:%d bearish:%d)' % (
            sentiment.get('article_count', 0),
            sentiment.get('bullish_count', 0),
            sentiment.get('neutral_count', 0),
            sentiment.get('bearish_count', 0),
        )))
        lines.append(_pad('Trend', '%s' % sentiment.get('sentiment_trend', 'stable')))

        # Top terms
        top_pos = sentiment.get('top_positive_terms', [])
        top_neg = sentiment.get('top_negative_terms', [])
        if top_pos:
            pos_str = ', '.join('%s(%d)' % (t, c) for t, c in top_pos[:4])
            lines.append(_pad('Bullish words', pos_str))
        if top_neg:
            neg_str = ', '.join('%s(%d)' % (t, c) for t, c in top_neg[:4])
            lines.append(_pad('Bearish words', neg_str))

        # Recent article headlines
        articles = sentiment.get('articles', [])
        if articles:
            lines.append('')
            lines.append('  [Recent News Headlines]')
            for i, art in enumerate(articles[:8]):
                emoji = {'bullish': '🟢', 'neutral': '🟡', 'bearish': '🔴'}.get(art['label'], '⚪')
                lines.append('  %s %s | %s' % (emoji, art.get('date', ''), art['title'][:70]))
    except Exception as e:
        lines.append('')
        lines.append('--- Sentiment (舆情分析) ---')
        lines.append(_pad('Status', 'Unavailable (%s)' % str(e)[:40]))

    # Overall
    score = get_score(trend, fund_total, basic_score, detail)
    signal = get_signal(score)
    signal_cn = get_signal_cn(signal)

    lines.append('')
    lines.append('--- Overall ---')
    lines.append(_pad('Score', '%d/100' % score))
    lines.append(_pad('Signal', '%s (%s)' % (signal_cn, signal)))

    summaries = {
        'strong_buy': 'Strong bullish across dimensions',
        'buy': 'Mostly positive, watch for entry',
        'hold': 'Mixed signals, cautious holding',
        'reduce': 'Bearish tendency, consider reducing',
        'avoid': 'Strong bearish, avoid',
    }
    lines.append(_pad('Summary', summaries.get(signal, '')))

    lines.append('')
    lines.append('=' * 60)
    lines.append('  Disclaimer: Automated analysis, not investment advice.')
    lines.append('=' * 60)

    return chr(10).join(lines)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(generate_report(sys.argv[1]))
    else:
        print("Usage: python report.py <symbol>")
