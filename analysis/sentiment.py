"""
Sentiment analysis module for Chinese financial news.
Uses dictionary-based approach with weighted lexicon.
No external NLP dependencies — pure Python.

Scoring: -1.0 (extremely bearish) to +1.0 (extremely bullish)
Classification: bullish (>0.2), neutral (-0.2~0.2), bearish (<-0.2)
"""

import re
from datetime import datetime, timedelta
from collections import Counter


# ═══════════════════════════════════════════════════════════════════════════════
#  Chinese Financial Sentiment Lexicon
# ═══════════════════════════════════════════════════════════════════════════════

# ── Positive (Bullish) Terms ──────────────────────────────────────────────────

POSITIVE_TERMS = {
    # Strong bullish — weight 2.0
    '涨停': 2.0, '利好': 2.0, '大增': 2.0, '暴涨': 2.0, '突破': 2.0,
    '创新高': 2.0, '超预期': 2.0, '强势上攻': 2.0, '大幅增长': 2.0,
    '涨停板': 2.0, '封板': 2.0, '一字板': 2.0, '连板': 2.0,
    '业绩大增': 2.0, '利润大增': 2.0, '营收大增': 2.0,
    '高增长': 2.0, '爆发式增长': 2.0, '净利润大增': 2.0,
    '重大利好': 2.0, '政策利好': 2.0, '行业利好': 2.0,
    '超预期增长': 2.0, '翻倍': 2.0, '暴涨超': 2.0,

    # Moderate bullish — weight 1.5
    '增持': 1.5, '买入': 1.5, '推荐': 1.5, '看好': 1.5,
    '反弹': 1.5, '大涨': 1.5, '回升': 1.5, '回暖': 1.5,
    '扭亏为盈': 1.5, '扩张': 1.5, '加仓': 1.5,
    '放量上涨': 1.5, '量价齐升': 1.5, '机构买入': 1.5,
    '北向资金流入': 1.5, '主力净流入': 1.5, '资金流入': 1.5,
    '超配': 1.5, '上调评级': 1.5, '上调目标价': 1.5,
    '业绩改善': 1.5, '盈利能力提升': 1.5, '毛利提升': 1.5,
    '中标': 1.5, '签约': 1.5, '订单': 1.5,

    # Mild bullish — weight 1.0
    '增长': 1.0, '盈利': 1.0, '分红': 1.0, '回购': 1.0,
    '涨幅': 1.0, '上升': 1.0, '改善': 1.0, '走强': 1.0,
    '领涨': 1.0, '走牛': 1.0, '发力': 1.0, '净流入': 1.0,
    '景气': 1.0, '受益': 1.0, '布局': 1.0, '布局机会': 1.0,
    '估值修复': 1.0, '价值回归': 1.0, '配置价值': 1.0,
    '买入评级': 1.0, '增持评级': 1.0, '跑赢': 1.0,
    '派息': 1.0, '高送转': 1.0, '送转': 1.0,
    '稳健增长': 1.0, '稳步增长': 1.0, '稳中有升': 1.0,
    '产能释放': 1.0, '新产品': 1.0, '技术突破': 1.0,
    '研发投入': 1.0, '获得专利': 1.0,
    # Extended positive terms (v2)
    '稳健': 1.0, '大放异彩': 1.5, '成效': 1.0, '赚钱': 1.0,
    '最赚钱': 1.5, '开门红': 1.5, '亮眼': 1.5, '靓丽': 1.5,
    '亮丽': 1.5, '优异': 1.5, '优秀': 1.0, '积极': 1.0,
    '释放': 0.8, '空间': 0.5, '潜力': 0.8,
    '渠道改革': 1.0, '市场化改革': 1.0, '改革成效': 1.0,
    '新突破': 1.5, '突破性': 1.5, '历史新高': 2.0,
    '业绩亮眼': 1.5, '利润亮眼': 1.5, '表现亮眼': 1.5,
    '超预期增长': 2.0, '业绩超预期': 2.0, '利润超预期': 2.0,
    '景气度': 1.0, '高景气': 1.5, '持续景气': 1.5,
    '价值重估': 1.5, '估值提升': 1.0, '戴维斯双击': 2.0,
    '龙头': 0.5, '行业龙头': 1.0, '头部': 0.5,
    '性价比': 0.5, '高性价比': 1.0, '低估值': 1.0,
    '底部': 0.3, '见底': 1.0, '筑底': 1.0, '触底': 1.0,
    '拐点': 1.5, '业绩拐点': 2.0, '向上拐点': 2.0,
    '反转': 1.5, '困境反转': 2.0,
    # v3 additions (from 000001 analysis)
    '拉升': 1.0, '涨超': 1.0, '大涨超': 1.5, '走牛': 1.0,
    '正增': 1.0, '回正': 1.5, '企稳': 1.0, '过峰': 1.0,
    '上行': 1.0, '走高': 1.0, '攀升': 1.0, '冲高': 0.8,
    '止跌': 1.5, '企稳回升': 1.5, '探底回升': 1.5,
}


# ── Negative (Bearish) Terms ──────────────────────────────────────────────────

NEGATIVE_TERMS = {
    # Strong bearish — weight 2.0
    '跌停': 2.0, '利空': 2.0, '暴跌': 2.0, '破位': 2.0,
    '创新低': 2.0, '大幅下滑': 2.0, '严重亏损': 2.0,
    '跌停板': 2.0, '持续下跌': 2.0, '断崖式下跌': 2.0,
    '业绩暴雷': 2.0, '财务造假': 2.0, '退市': 2.0,
    '暂停上市': 2.0, '停牌': 2.0,
    '重大利空': 2.0, '黑天鹅': 2.0, '系统性风险': 2.0,
    '资金链断裂': 2.0, '债务违约': 2.0, '破产': 2.0,
    '被查': 2.0, '被调查': 2.0, '立案调查': 2.0,

    # Moderate bearish — weight 1.5
    '减持': 1.5, '卖出': 1.5, '看空': 1.5, '大跌': 1.5,
    '跳水': 1.5, '下挫': 1.5, '违规': 1.5, '调查': 1.5,
    '下滑': 1.5, '亏损': 1.5, '预亏': 1.5,
    '业绩下滑': 1.5, '利润下滑': 1.5, '营收下滑': 1.5,
    '放量下跌': 1.5, '缩量下跌': 1.5,
    '北向资金流出': 1.5, '主力净流出': 1.5, '资金流出': 1.5,
    '减持评级': 1.5, '下调评级': 1.5, '下调目标价': 1.5,
    '清仓': 1.5, '减仓': 1.5, '套现': 1.5,
    '处罚': 1.5, '罚款': 1.5, '诉讼': 1.5,
    '冻结': 1.5, '质押': 1.5, '高质押': 1.5,

    # Mild bearish — weight 1.0
    '下跌': 1.0, '下降': 1.0, '减少': 1.0, '走弱': 1.0,
    '领跌': 1.0, '走熊': 1.0, '疲软': 1.0, '低迷': 1.0,
    '低于预期': 1.0, '不及预期': 1.0, '未达预期': 1.0,
    '承压': 1.0, '拖累': 1.0, '压力': 1.0,
    'ST': 1.0, '*ST': 1.0, '被ST': 1.0,
    '估值偏高': 1.0, '估值过高': 1.0, '泡沫': 1.0,
    '毛利率下降': 1.0, '净利率下降': 1.0, 'ROE下降': 1.0,
    '解禁': 1.0, '大规模解禁': 1.5,
    '高负债': 1.0, '负债率': 1.0,
    # Extended negative terms (v2)
    '腰斩': 2.0, '崩盘': 2.0, '闪崩': 2.0, '踩踏': 2.0,
    '爆仓': 2.0, '穿仓': 2.0, '强平': 2.0,
    '雷': 1.5, '暴雷': 2.0, '踩雷': 2.0,
    '计提': 1.0, '计提减值': 1.5, '商誉减值': 2.0,
    '应收账款': 0.5, '坏账': 1.5, '逾期': 1.5,
    '问询函': 1.5, '关注函': 1.5, '监管函': 2.0,
    '警示函': 1.5, '通报批评': 1.5, '公开谴责': 2.0,
    '限售': 1.0, '限售股': 1.0, '减持计划': 1.5,
    '预降': 1.5, '预减': 1.5, '业绩预降': 2.0,
    '资金紧张': 2.0, '流动性': 0.5, '流动性紧张': 1.5,
    '收窄': 1.0, '萎缩': 1.5, '加剧': 1.5,
    '恶化': 2.0, '恶化趋势': 2.0,
    '停产': 1.5, '停工': 1.5, '关闭': 1.5,
    '裁撤': 1.5, '裁员': 1.5,
}


# ── Modifiers (amplify or diminish term weight) ───────────────────────────────

MODIFIERS = {
    # Amplifiers
    '大幅': 2.0, '剧烈': 2.0, '连续': 1.5, '持续': 1.3,
    '大幅增长': 2.0, '大幅下滑': 2.0, '巨额': 2.0, '严重': 2.0,
    '连续涨停': 2.0, '连续跌停': 2.0, '连续大涨': 1.8,
    '连续下跌': 1.8, '多次': 1.3, '再度': 1.3,
    '大举': 1.5, '加速': 1.5, '全面': 1.3, '全线': 1.3,
    '超': 1.3,  # 涨超, 增超

    # Diminishers
    '小幅': 0.5, '略': 0.5, '略有': 0.5, '轻微': 0.5,
    '暂时': 0.7, '短期': 0.7, '微': 0.4,
}

# ── Context words (neutralize sentiment) ──────────────────────────────────────

CONTEXT_NEUTRALIZERS = [
    '如果', '假设', '可能', '或许', '或许会',
    '展望', '推测', '猜测',
]
# NOTE: '预期' is NOT a neutralizer — it appears in '超预期' (bullish), '低于预期' (bearish)
# '符合预期' is handled as a standalone phrase below

# Sub-phrases that indicate neutral/speculative tone ONLY when standalone
# (not part of a compound financial term)
NEUTRALIZER_PATTERNS = [
    r'(?<!超)(?<!符合)(?<!低于)(?<!不及)(?<!未达)(?<!好于)预期(?!增长)(?!之内)',
    r'(?<!业)预计(?!增)(?!大)',
]

# ── Recency weight decay (hours) ──────────────────────────────────────────────
# News older than this gets progressively discounted
RECENCY_HALF_LIFE = 48  # hours — half weight after 48h


# ═══════════════════════════════════════════════════════════════════════════════
#  Analysis Functions
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_text(text: str) -> dict:
    """
    Analyze a single text string for financial sentiment.

    Args:
        text: Chinese text to analyze (typically a news title)

    Returns:
        dict with keys: score, label, positive_terms, negative_terms, modifiers
    """
    pos_score = 0.0
    neg_score = 0.0
    pos_found = []
    neg_found = []
    mods_found = []

    # Check for longer terms first (避免短词误匹配)
    # Sort by length descending
    all_pos = sorted(POSITIVE_TERMS.items(), key=lambda x: -len(x[0]))
    all_neg = sorted(NEGATIVE_TERMS.items(), key=lambda x: -len(x[0]))

    matched_positions = set()

    # Scan for positive terms
    for term, weight in all_pos:
        for match in re.finditer(re.escape(term), text):
            start, end = match.span()
            # Avoid double-counting overlapping terms
            if any(start <= p < end or p <= start < p + 5 for p in matched_positions):
                continue
            matched_positions.add(start)

            # Check for modifiers near the term
            context = text[max(0, start - 6):end + 6]
            mod_weight = 1.0
            mod_name = None
            for mod, mod_w in sorted(MODIFIERS.items(), key=lambda x: -len(x[0])):
                if mod in context:
                    mod_weight *= mod_w
                    mod_name = mod
                    mods_found.append(mod)
                    break

            effective = weight * mod_weight
            pos_score += effective
            pos_found.append({'term': term, 'weight': weight, 'effective': effective,
                              'modifier': mod_name})

    # Scan for negative terms
    matched_positions.clear()
    for term, weight in all_neg:
        for match in re.finditer(re.escape(term), text):
            start, end = match.span()
            if any(start <= p < end or p <= start < p + 5 for p in matched_positions):
                continue
            matched_positions.add(start)

            context = text[max(0, start - 6):end + 6]
            mod_weight = 1.0
            mod_name = None
            for mod, mod_w in sorted(MODIFIERS.items(), key=lambda x: -len(x[0])):
                if mod in context:
                    mod_weight *= mod_w
                    mod_name = mod
                    mods_found.append(mod)
                    break

            effective = weight * mod_weight
            neg_score += effective
            neg_found.append({'term': term, 'weight': weight, 'effective': effective,
                              'modifier': mod_name})

    # Check if context neutralizers are present (减弱信号)
    has_neutralizer = any(n in text for n in CONTEXT_NEUTRALIZERS)
    # Also check regex patterns for partial neutralizers
    if not has_neutralizer:
        for pat in NEUTRALIZER_PATTERNS:
            if re.search(pat, text):
                has_neutralizer = True
                break
    if has_neutralizer:
        pos_score *= 0.5
        neg_score *= 0.5
        mods_found.append('(含推测性词语)')

    # Compute net score, clamp to [-1, 1]
    net = pos_score - neg_score
    # Normalize: use sigmoid-like scaling to keep in range
    net = max(-1.0, min(1.0, net / max(1.0, abs(net) * 0.5 + 2.0)))

    # Classification
    if net > 0.2:
        label = 'bullish'
    elif net < -0.2:
        label = 'bearish'
    else:
        label = 'neutral'

    return {
        'score': round(net, 3),
        'label': label,
        'positive_terms': pos_found,
        'negative_terms': neg_found,
        'modifiers': mods_found,
        'text': text[:100],
    }


def analyze_news(news_items: list) -> dict:
    """
    Analyze a list of news items and compute aggregate sentiment.

    Args:
        news_items: List of news dicts from data/news.py, each with
                    'title', 'date', 'time' keys

    Returns:
        dict with keys: overall_score, overall_label, article_count,
                        bullish_count, bearish_count, neutral_count,
                        articles (list of per-article results),
                        key_terms (most frequent terms),
                        sentiment_trend (recent direction)
    """
    if not news_items:
        return {
            'overall_score': 0.0,
            'overall_label': 'neutral',
            'error': 'No news items to analyze',
        }

    results = []
    total_score = 0.0
    bullish_count = 0
    bearish_count = 0
    neutral_count = 0
    all_pos_terms = []
    all_neg_terms = []

    now = datetime.now()

    for item in news_items:
        title = item.get('title', '')
        if not title:
            continue

        analysis = analyze_text(title)

        # Apply recency weight
        recency_weight = 1.0
        date_str = item.get('date', '')
        time_str = item.get('time', '')
        if date_str and time_str:
            try:
                article_time = datetime.strptime(
                    f'{date_str} {time_str}', '%Y-%m-%d %H:%M'
                )
                hours_ago = (now - article_time).total_seconds() / 3600
                if hours_ago > 0:
                    recency_weight = 0.5 ** (hours_ago / RECENCY_HALF_LIFE)
            except ValueError:
                pass

        weighted_score = analysis['score'] * recency_weight
        total_score += weighted_score

        article_result = {
            'title': title[:80],
            'date': date_str,
            'score': analysis['score'],
            'label': analysis['label'],
            'recency_weight': round(recency_weight, 2),
            'weighted_score': round(weighted_score, 3),
            'key_terms': [t['term'] for t in analysis['positive_terms']] +
                         [t['term'] for t in analysis['negative_terms']],
        }
        results.append(article_result)

        if analysis['label'] == 'bullish':
            bullish_count += 1
        elif analysis['label'] == 'bearish':
            bearish_count += 1
        else:
            neutral_count += 1

        for t in analysis['positive_terms']:
            all_pos_terms.append(t['term'])
        for t in analysis['negative_terms']:
            all_neg_terms.append(t['term'])

    # Normalize total score
    n = max(1, len(results))
    overall_score = total_score / n
    overall_score = max(-1.0, min(1.0, overall_score))

    if overall_score > 0.2:
        overall_label = 'bullish'
    elif overall_score < -0.2:
        overall_label = 'bearish'
    else:
        overall_label = 'neutral'

    # Get most frequent terms
    pos_counter = Counter(all_pos_terms)
    neg_counter = Counter(all_neg_terms)

    # Compute sentiment trend: compare recent (last 5) vs older
    trend = 'stable'
    if len(results) >= 4:
        recent = results[:min(5, len(results)//2)]
        older = results[min(5, len(results)//2):]
        recent_avg = sum(r['score'] for r in recent) / max(1, len(recent))
        older_avg = sum(r['score'] for r in older) / max(1, len(older))
        if recent_avg - older_avg > 0.15:
            trend = 'improving'
        elif recent_avg - older_avg < -0.15:
            trend = 'deteriorating'

    return {
        'overall_score': round(overall_score, 3),
        'overall_label': overall_label,
        'article_count': len(results),
        'bullish_count': bullish_count,
        'bearish_count': bearish_count,
        'neutral_count': neutral_count,
        'articles': results,
        'top_positive_terms': pos_counter.most_common(5),
        'top_negative_terms': neg_counter.most_common(5),
        'sentiment_trend': trend,
    }


def get_sentiment_for_stock(symbol: str, use_llm: bool = False, use_cache: bool = True) -> dict:
    """
    Convenience function: fetch news and analyze sentiment in one call.

    Args:
        symbol: Stock code, e.g. '600519'
        use_llm: If True, use DeepSeek LLM for nuanced sentiment (with local learning cache)
        use_cache: If True and use_llm=True, check learned store before calling API

    Returns:
        Full sentiment analysis dict with news summary.
        When use_llm=True, includes "llm_used", "key_themes", "learning_store_stats".
    """
    from data.news import get_stock_news, get_market_news

    if use_llm:
        try:
            from analysis.sentiment_llm import get_sentiment_llm
            result = get_sentiment_llm(symbol, use_cache=use_cache)
            result['symbol'] = symbol
            result['fetched_at'] = __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            return result
        except Exception as e:
            # Fallback to dictionary if LLM module fails
            pass

    stock_news = get_stock_news(symbol, max_items=20)
    market_news = get_market_news(max_items=10)

    stock_sentiment = analyze_news(stock_news)

    return {
        'symbol': symbol,
        'stock_sentiment': stock_sentiment,
        'news_count': len(stock_news),
        'market_news_count': len(market_news),
        'fetched_at': __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
