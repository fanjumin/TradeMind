"""
LLM-based Sentiment Analysis for Chinese Financial News.
Architecture:
  1. Cache-first: check local learning store before calling API
  2. LLM analysis: call DeepSeek API with structured prompt for nuanced scoring
  3. Local learning: save all results to JSON store for future reference
  4. Hybrid fallback: use static dictionary when API unavailable
  5. Batch support: send multiple articles in one API call to minimize cost

Local Learning Store: data/sentiment_learned.json
  - sha256(title) → {score, label, reasoning, confidence, model, timestamp, usage}
  - Grows over time, reducing API dependency
  - Can be used to fine-tune or improve the static dictionary
"""
import json
import os
import hashlib
import time
from datetime import datetime
from typing import List, Dict, Optional, Tuple


# ─── Paths ─────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
LEARNED_STORE = os.path.join(DATA_DIR, 'sentiment_learned.json')
CONFIG_PATH = os.path.join(BASE_DIR, 'api_config.json')

# DeepSeek API settings (reuse from llm_advisor.py)
DEEPSEEK_BASE = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"


# ─── Local Learning Store ──────────────────────────────────

class SentimentLearnedStore:
    """Persistent store of LLM-analyzed sentiment results.
    Keyed by sha256 hash of article title for dedup.
    """

    def __init__(self, path: str = None):
        self.path = path or LEARNED_STORE
        self.data: Dict[str, dict] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]

    def get(self, title: str) -> Optional[dict]:
        """Look up cached sentiment for a title."""
        key = self._hash(title)
        return self.data.get(key)

    def put(self, title: str, result: dict):
        """Store sentiment result for a title."""
        key = self._hash(title)
        result['_cached_at'] = datetime.now().isoformat()
        result['_title_hash'] = key
        self.data[key] = result
        self._save()

    def stats(self) -> dict:
        """Return store statistics."""
        total = len(self.data)
        bullish = sum(1 for v in self.data.values() if v.get('label') == 'bullish')
        bearish = sum(1 for v in self.data.values() if v.get('label') == 'bearish')
        neutral = total - bullish - bearish
        models = {}
        for v in self.data.values():
            m = v.get('model', 'unknown')
            models[m] = models.get(m, 0) + 1
        return {
            'total_learned': total,
            'bullish': bullish,
            'bearish': bearish,
            'neutral': neutral,
            'models_used': models,
            'store_path': self.path,
        }

    def export_training_data(self) -> List[dict]:
        """Export as list of {title, label, score, reasoning} for potential fine-tuning."""
        return [
            {
                'title': v.get('title', ''),
                'label': v.get('label', 'neutral'),
                'score': v.get('score', 0),
                'reasoning': v.get('reasoning', ''),
                'model': v.get('model', ''),
            }
            for v in self.data.values()
        ]


# ─── API Call ──────────────────────────────────────────────

def _load_api_key() -> Optional[str]:
    """Load DeepSeek API key from config or env."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
            key = cfg.get('deepseek_api_key')
            if key:
                return key
        except Exception:
            pass
    return os.environ.get('DEEPSEEK_API_KEY')


def _get_proxy() -> Optional[str]:
    """Get HTTPS proxy URL."""
    return (os.environ.get('HTTPS_PROXY') or
            os.environ.get('https_proxy') or
            'http://127.0.0.1:10809')


def call_llm_sentiment(titles: List[str], api_key: str = None, model: str = None) -> dict:
    """Call DeepSeek API to analyze sentiment of multiple news titles in one batch.

    Args:
        titles: List of news titles (max 15 per batch for cost efficiency)
        api_key: DeepSeek API key
        model: Model name (default: deepseek-chat)

    Returns:
        dict with 'results' (list of per-title analysis), 'usage', 'model'
        or 'error' key on failure
    """
    import urllib.request
    import urllib.error

    if api_key is None:
        api_key = _load_api_key()

    if not api_key:
        return {'error': 'No API key configured. Set DEEPSEEK_API_KEY or update api_config.json'}

    if model is None:
        model = DEFAULT_MODEL

    # Build prompt
    titles_text = '\n'.join(f"{i+1}. {t}" for i, t in enumerate(titles))

    system_prompt = """你是一个专业的A股财经新闻情绪分析专家。你的任务是对给定的新闻标题进行情绪评分。

评分规则（-1.0 到 +1.0）：
- +0.8 ~ +1.0：强烈看多（重大利好，如业绩暴增、政策扶持、行业爆发）
- +0.3 ~ +0.8：温和看多（正面消息，如订单增长、股东增持、行业回暖）
- -0.3 ~ +0.3：中性或混合（常规公告、人事变动、或利好利空并存）
- -0.8 ~ -0.3：温和看空（负面消息，如业绩下滑、减持、监管关注）
- -1.0 ~ -0.8：强烈看空（重大利空，如财务造假、立案调查、退市风险）

分析维度（每篇文章都需分析）：
1. 对股价的直接影响方向
2. 影响的持续性（短期/中期/长期）
3. 消息的可信度与权威性

输出格式：严格JSON数组，每个元素包含：
{
  "index": 文章序号,
  "score": 情绪分数(-1.0到1.0, 一位小数),
  "label": "bullish"或"bearish"或"neutral",
  "confidence": 置信度(0.0到1.0),
  "reasoning": 简短分析理由(20字以内),
  "impact_duration": "short"或"medium"或"long",
  "key_factors": ["关键词1", "关键词2"]
}

只输出JSON数组，不要有任何其他文字。"""

    user_prompt = f"请分析以下{len(titles)}条A股相关新闻标题的情绪：\n\n{titles_text}"

    url = f"{DEEPSEEK_BASE}/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"}  # Force JSON output
    }).encode('utf-8')

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
    }

    proxy_url = _get_proxy()
    proxy_handler = urllib.request.ProxyHandler({
        'http': proxy_url,
        'https': proxy_url,
    })
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(url, data=payload, headers=headers)

    try:
        resp = opener.open(req, timeout=60)
        result = json.loads(resp.read())

        if 'choices' not in result or len(result['choices']) == 0:
            return {'error': f'API returned no choices: {result}', 'raw': result}

        content = result['choices'][0]['message']['content']

        # Parse JSON response
        try:
            parsed = json.loads(content)
            # Handle both {"results": [...]} and direct [...] formats
            if isinstance(parsed, dict) and 'results' in parsed:
                analysis_list = parsed['results']
            elif isinstance(parsed, list):
                analysis_list = parsed
            else:
                return {'error': f'Unexpected response format: {type(parsed)}', 'raw_content': content}
        except json.JSONDecodeError:
            # Try to extract JSON from text
            import re
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                try:
                    analysis_list = json.loads(match.group())
                except json.JSONDecodeError:
                    return {'error': 'Could not parse JSON response', 'raw_content': content}
            else:
                return {'error': 'Could not find JSON in response', 'raw_content': content}

        return {
            'results': analysis_list,
            'usage': result.get('usage', {}),
            'model': result.get('model', model),
        }

    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ''
        return {'error': f'HTTP {e.code}: {body}'}
    except Exception as e:
        return {'error': str(e)}


# ─── Main Analyzer ─────────────────────────────────────────

class LLMSentimentAnalyzer:
    """LLM-based sentiment analyzer with local learning and cache."""

    def __init__(self, store: SentimentLearnedStore = None, batch_size: int = 10):
        self.store = store or SentimentLearnedStore()
        self.batch_size = batch_size
        self._api_key = None

    @property
    def api_key(self):
        if self._api_key is None:
            self._api_key = _load_api_key()
        return self._api_key

    def analyze_articles(self, news_items: List[dict],
                         force_llm: bool = False,
                         use_cache: bool = True) -> dict:
        """Analyze a list of news articles.

        Args:
            news_items: List of news dicts (each with 'title', 'date', 'time')
            force_llm: If True, skip cache and always call LLM
            use_cache: If False, skip cache lookup (but still save results)

        Returns:
            dict with overall score, label, per-article results, learning stats
        """
        if not news_items:
            return {
                'overall_score': 0.0,
                'overall_label': 'neutral',
                'llm_used': False,
                'articles': [],
                'error': 'No news items to analyze',
            }

        results = []
        api_calls = 0
        cache_hits = 0
        uncached_titles = []
        uncached_indices = []

        # Phase 1: Check cache for each article
        for i, item in enumerate(news_items):
            title = item.get('title', '')
            if not title:
                results.append(self._make_neutral(item, 'empty_title'))
                continue

            if use_cache and not force_llm:
                cached = self.store.get(title)
                if cached:
                    results.append({
                        'title': title[:80],
                        'date': item.get('date', ''),
                        'score': cached.get('score', 0),
                        'label': cached.get('label', 'neutral'),
                        'confidence': cached.get('confidence', 0.5),
                        'reasoning': cached.get('reasoning', ''),
                        'impact_duration': cached.get('impact_duration', 'short'),
                        'key_factors': cached.get('key_factors', []),
                        'source': 'cache',
                        'model': cached.get('model', ''),
                    })
                    cache_hits += 1
                    continue

            uncached_titles.append(title)
            uncached_indices.append(i)
            results.append(None)  # placeholder

        # Phase 2: Call LLM for uncached articles in batches
        if uncached_titles and self.api_key:
            for batch_start in range(0, len(uncached_titles), self.batch_size):
                batch_end = min(batch_start + self.batch_size, len(uncached_titles))
                batch_titles = uncached_titles[batch_start:batch_end]
                batch_indices = uncached_indices[batch_start:batch_end]

                llm_result = call_llm_sentiment(batch_titles, self.api_key)
                api_calls += 1

                if 'error' in llm_result:
                    # LLM failed — use dictionary fallback for these items
                    for idx in batch_indices:
                        from analysis.sentiment import analyze_text as dict_analyze
                        item = news_items[idx]
                        dict_result = dict_analyze(item.get('title', ''))
                        results[idx] = {
                            'title': item.get('title', '')[:80],
                            'date': item.get('date', ''),
                            'score': dict_result.get('score', 0),
                            'label': dict_result.get('label', 'neutral'),
                            'confidence': 0.3,
                            'reasoning': 'dictionary_fallback',
                            'impact_duration': 'short',
                            'key_factors': [],
                            'source': 'dictionary',
                            'model': 'local_dict',
                        }
                    continue

                # Process LLM results
                llm_analyses = llm_result.get('results', [])
                for analysis in llm_analyses:
                    analysis_idx = analysis.get('index', 0) - 1  # 1-based to 0-based
                    if 0 <= analysis_idx < len(batch_titles):
                        original_idx = batch_indices[analysis_idx]
                        item = news_items[original_idx]
                        title = item.get('title', '')

                        entry = {
                            'title': title[:80],
                            'date': item.get('date', ''),
                            'score': float(analysis.get('score', 0)),
                            'label': analysis.get('label', 'neutral'),
                            'confidence': float(analysis.get('confidence', 0.7)),
                            'reasoning': analysis.get('reasoning', ''),
                            'impact_duration': analysis.get('impact_duration', 'short'),
                            'key_factors': analysis.get('key_factors', []),
                            'source': 'llm',
                            'model': llm_result.get('model', 'unknown'),
                        }
                        results[original_idx] = entry

                        # Save to learning store
                        self.store.put(title, {
                            'title': title,
                            'score': entry['score'],
                            'label': entry['label'],
                            'confidence': entry['confidence'],
                            'reasoning': entry['reasoning'],
                            'impact_duration': entry['impact_duration'],
                            'key_factors': entry['key_factors'],
                            'model': entry['model'],
                        })

                # Small delay between batches to avoid rate limits
                if batch_end < len(uncached_titles):
                    time.sleep(0.5)

        elif uncached_titles:
            # No API key — dictionary fallback
            from analysis.sentiment import analyze_text as dict_analyze
            for idx in uncached_indices:
                item = news_items[idx]
                dict_result = dict_analyze(item.get('title', ''))
                results[idx] = {
                    'title': item.get('title', '')[:80],
                    'date': item.get('date', ''),
                    'score': dict_result.get('score', 0),
                    'label': dict_result.get('label', 'neutral'),
                    'confidence': 0.3,
                    'reasoning': 'no_api_key',
                    'impact_duration': 'short',
                    'key_factors': [],
                    'source': 'dictionary',
                    'model': 'local_dict',
                }

        # Phase 3: Compute aggregate
        valid_results = [r for r in results if r is not None]
        return self._aggregate(valid_results, api_calls, cache_hits, news_items)

    def _make_neutral(self, item: dict, reason: str) -> dict:
        return {
            'title': item.get('title', '')[:80],
            'date': item.get('date', ''),
            'score': 0.0,
            'label': 'neutral',
            'confidence': 0.0,
            'reasoning': reason,
            'impact_duration': 'short',
            'key_factors': [],
            'source': 'none',
            'model': '',
        }

    def _aggregate(self, results: list, api_calls: int, cache_hits: int,
                   news_items: list) -> dict:
        """Aggregate per-article results into overall sentiment."""
        if not results:
            return {
                'overall_score': 0.0,
                'overall_label': 'neutral',
                'llm_used': False,
                'articles': [],
            }

        total_score = 0.0
        bullish_count = bearish_count = neutral_count = 0
        llm_used = any(r.get('source') == 'llm' for r in results)
        now = datetime.now()

        for r in results:
            # Apply recency weight
            recency_weight = 1.0
            date_str = r.get('date', '')
            if date_str:
                try:
                    article_time = datetime.strptime(date_str, '%Y-%m-%d')
                    hours_ago = max(0, (now - article_time).total_seconds() / 3600)
                    if hours_ago > 0:
                        recency_weight = 0.5 ** (hours_ago / 48)  # half-life 48h for news
                except ValueError:
                    pass

            confidence = r.get('confidence', 0.5)
            weighted_score = r['score'] * recency_weight * max(0.3, confidence)
            total_score += weighted_score

            r['recency_weight'] = round(recency_weight, 2)
            r['weighted_score'] = round(weighted_score, 3)

            if r['label'] == 'bullish':
                bullish_count += 1
            elif r['label'] == 'bearish':
                bearish_count += 1
            else:
                neutral_count += 1

        n = max(1, len(results))
        overall_score = max(-1.0, min(1.0, total_score / n))

        if overall_score > 0.25:
            overall_label = 'bullish'
        elif overall_score < -0.25:
            overall_label = 'bearish'
        else:
            overall_label = 'neutral'

        # Sentiment trend
        trend = 'stable'
        if len(results) >= 4:
            recent = results[:min(5, len(results) // 2)]
            older = results[min(5, len(results) // 2):]
            recent_avg = sum(r['score'] for r in recent) / max(1, len(recent))
            older_avg = sum(r['score'] for r in older) / max(1, len(older))
            if recent_avg - older_avg > 0.2:
                trend = 'improving'
            elif recent_avg - older_avg < -0.2:
                trend = 'deteriorating'

        # Key themes from LLM analysis
        all_factors = []
        for r in results:
            all_factors.extend(r.get('key_factors', []))

        from collections import Counter
        factor_counts = Counter(all_factors)

        return {
            'overall_score': round(overall_score, 3),
            'overall_label': overall_label,
            'article_count': len(results),
            'bullish_count': bullish_count,
            'bearish_count': bearish_count,
            'neutral_count': neutral_count,
            'articles': results,
            'sentiment_trend': trend,
            'key_themes': factor_counts.most_common(8),
            'llm_used': llm_used,
            'api_calls': api_calls,
            'cache_hits': cache_hits,
            'learning_store': self.store.stats(),
        }


# ─── Convenience function ─────────────────────────────────

def get_sentiment_llm(symbol: str, use_cache: bool = True) -> dict:
    """Full pipeline: fetch news → LLM sentiment analysis → return result.
    This is the drop-in replacement for sentiment.get_sentiment_for_stock().
    """
    from data.news import get_stock_news

    news = get_stock_news(symbol, max_items=20)

    if not news or (len(news) == 1 and 'error' in news[0]):
        return {
            'error': news[0].get('error', 'Failed to fetch news') if news else 'No news',
            'overall_score': 0.0,
            'overall_label': 'neutral',
            'stock_sentiment': {'overall_score': 0, 'overall_label': 'neutral'},
        }

    analyzer = LLMSentimentAnalyzer()
    result = analyzer.analyze_articles(news, use_cache=use_cache)

    # Maintain backward compatibility with sentiment.py's get_sentiment_for_stock()
    return {
        'stock_sentiment': {
            'overall_score': result['overall_score'],
            'overall_label': result['overall_label'],
            'article_count': result['article_count'],
            'bullish_count': result['bullish_count'],
            'bearish_count': result['bearish_count'],
            'neutral_count': result['neutral_count'],
            'sentiment_trend': result['sentiment_trend'],
        },
        'articles': result['articles'],
        'key_themes': result.get('key_themes', []),
        'llm_used': result['llm_used'],
        'api_calls': result.get('api_calls', 0),
        'cache_hits': result.get('cache_hits', 0),
        'learning_store_stats': result.get('learning_store', {}),
    }


if __name__ == '__main__':
    # Quick test
    test_titles = [
        "重磅！茅台集团宣布提价20%，明年业绩有望大幅增长",
        "监管层再出手，严查上市公司财务造假",
        "北向资金今日净流入超百亿，外资持续加仓A股",
        "某公司高管集体减持，套现超10亿元",
    ]
    result = call_llm_sentiment(test_titles)
    if 'error' in result:
        print(f"Error: {result['error']}")
    else:
        for r in result['results']:
            print(f"[{r['label']:8s}] score={r['score']:+.1f} conf={r['confidence']:.1f} | {r['reasoning']}")
        print(f"\nUsage: {result.get('usage', {})}")
