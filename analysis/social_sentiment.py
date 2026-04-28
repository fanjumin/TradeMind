
"""
Social Media Sentiment Analysis for A-Stocks.
Data source: Eastmoney Guba (东方财富股吧) — stock discussion forum.
Architecture:
  1. Scrape: fetch Guba HTML, extract article_list JSON (title + full content + engagement data)
  2. Filter: exclude official/media accounts, keep real user posts
  3. LLM analysis: call DeepSeek API with prompt optimized for social media content
  4. Weighted aggregation: engagement-weighted bullish/bearish/neutral scoring
  5. Theme extraction: identify key discussion topics
  6. Caching: reuse SentimentLearnedStore pattern adapted for social posts

Integration:
  CLI:    python main.py --sentiment-social 600519
  Import: from analysis.social_sentiment import analyze_social_sentiment
"""

import json
import os
import re
import hashlib
import time
import math
import urllib.request
import urllib.error
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# ─── Paths ─────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
SOCIAL_STORE_PATH = os.path.join(DATA_DIR, 'social_sentiment_store.json')
CONFIG_PATH = os.path.join(BASE_DIR, 'api_config.json')

DEEPSEEK_BASE = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"

# ─── Constants ─────────────────────────────────────────────

GUBA_LIST_URL = "https://guba.eastmoney.com/list,{code},f.html"
GUBA_PAGE_URL = "https://guba.eastmoney.com/list,{code}_{page},f.html"

# Accounts to filter out (official media, not real user sentiment)
OFFICIAL_ACCOUNTS = {
    '贵州茅台资讯', '上市公司资讯', '财经评论', '证券时报',
    '每日经济新闻', '中国证券报', '上海证券报', '证券日报',
    '公司公告', '资讯', '公告解读',
    '平安银行资讯', '招商银行资讯', '兴业银行资讯',
}

# Also filter by user pattern: accounts ending with '资讯'
def _is_official(user: str) -> bool:
    if user in OFFICIAL_ACCOUNTS:
        return True
    if user.endswith('资讯'):
        return True
    return False

DEFAULT_PAGES = 2
MAX_PAGES = 5
BATCH_SIZE = 8

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


# ─── Helpers ───────────────────────────────────────────────

def _get_proxy() -> Optional[str]:
    return (os.environ.get('HTTPS_PROXY') or
            os.environ.get('https_proxy') or
            'http://127.0.0.1:10809')


def _load_api_key() -> Optional[str]:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
            key = cfg.get('deepseek_api_key')
            if key and key != '${DEEPSEEK_API_KEY}':
                return key
        except Exception:
            pass
    return os.environ.get('DEEPSEEK_API_KEY')


# ─── Social Sentiment Store ────────────────────────────────

class SocialSentimentStore:
    """Persistent store for social sentiment analysis results.
    Keyed by post_id for dedup. Separate from news sentiment store.
    """

    def __init__(self, path: str = None):
        self.path = path or SOCIAL_STORE_PATH
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

    def get(self, post_id: str) -> Optional[dict]:
        key = str(post_id)
        return self.data.get(key)

    def put(self, post_id: str, result: dict):
        key = str(post_id)
        result['_cached_at'] = datetime.now().isoformat()
        self.data[key] = result
        self._save()

    def stats(self) -> dict:
        total = len(self.data)
        bullish = sum(1 for v in self.data.values() if v.get('label') == 'bullish')
        bearish = sum(1 for v in self.data.values() if v.get('label') == 'bearish')
        return {
            'total_cached': total,
            'bullish': bullish,
            'bearish': bearish,
            'neutral': total - bullish - bearish,
            'store_path': self.path,
        }


# ─── Guba Scraper ──────────────────────────────────────────

def fetch_guba_posts(code: str, pages: int = DEFAULT_PAGES) -> List[dict]:
    """Fetch stock discussion posts from Eastmoney Guba."""
    all_posts = []
    proxy_url = _get_proxy()
    proxy_handler = urllib.request.ProxyHandler({
        'http': proxy_url,
        'https': proxy_url,
    })
    opener = urllib.request.build_opener(proxy_handler)

    for page in range(1, pages + 1):
        if page == 1:
            url = GUBA_LIST_URL.format(code=code)
        else:
            url = GUBA_PAGE_URL.format(code=code, page=page)

        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            resp = opener.open(req, timeout=15)
            html = resp.read().decode('utf-8', errors='replace')
        except Exception as e:
            print(f"  [WARN] Failed to fetch Guba page {page}: {e}")
            continue

        match = re.search(r'var article_list=(\{.*?\});', html, re.DOTALL)
        if not match:
            print(f"  [WARN] Could not find article_list on page {page}")
            continue

        try:
            data = json.loads(match.group(1))
            articles = data.get('re', [])
        except json.JSONDecodeError as e:
            print(f"  [WARN] JSON parse error on page {page}: {e}")
            continue

        for a in articles:
            post = {
                'post_id': str(a.get('post_id', '')),
                'title': a.get('post_title', '').strip(),
                'content': a.get('post_content', '').strip(),
                'user': a.get('user_nickname', '匿名'),
                'clicks': int(a.get('post_click_count', 0)),
                'comments': int(a.get('post_comment_count', 0)),
                'time': a.get('post_publish_time', a.get('post_last_time', '')),
                'stock_code': a.get('stockbar_code', code),
                'stock_name': a.get('stockbar_name', ''),
                'is_hot': bool(a.get('post_is_hot', False)),
            }

            if not post['title'] and not post['content']:
                continue
            if _is_official(post['user']):
                continue

            all_posts.append(post)

        if len(articles) < 80:
            break

        time.sleep(0.3)

    return all_posts


# ─── LLM Social Sentiment Analysis ─────────────────────────

SOCIAL_SYSTEM_PROMPT = """你是一个专业的A股投资者情绪分析专家。你的任务是分析股吧论坛帖子的情绪倾向和讨论主题。

每条帖子提供：标题、正文、阅读量、评论数、发布时间。

分析维度：
1. **情绪评分** (-1.0到+1.0):
   - +0.8~+1.0：强烈看多（坚定持有、抄底、长期看好、业绩超预期）
   - +0.3~+0.8：温和看多（逢低关注、估值合理、分红满意）
   - -0.3~+0.3：中性或观望（问询、技术讨论、不确定）
   - -0.8~-0.3：温和看空（减仓、估值偏高、行业下行）
   - -1.0~-0.8：强烈看空（清仓、暴雷预警、财务造假嫌疑）

2. **情绪标签**: "bullish" / "bearish" / "neutral"

3. **置信度** (0.0~1.0): 对评分的把握程度

4. **讨论主题** (1-3个关键词): 帖子在讨论什么（财报、估值、分红、政策、行业、技术面等）

5. **影响力评估** ("high"/"medium"/"low"): 结合阅读量和评论数判断该帖子的影响力

输出格式：严格JSON数组：
[{
  "index": 序号,
  "score": 情绪分数,
  "label": "bullish"或"bearish"或"neutral",
  "confidence": 置信度,
  "reasoning": "简短理由(20字内)",
  "topics": ["关键词1", "关键词2"],
  "influence": "high"或"medium"或"low"
}]

只输出JSON数组，不要有其他文字。"""


def call_llm_social(posts: List[dict], api_key: str = None, model: str = None) -> dict:
    """Call DeepSeek API to analyze social media posts in batch."""
    if api_key is None:
        api_key = _load_api_key()

    if not api_key:
        return {'error': 'No API key configured. Set DEEPSEEK_API_KEY or update api_config.json'}

    if model is None:
        model = DEFAULT_MODEL

    post_lines = []
    for i, p in enumerate(posts):
        content = p.get('content', '')[:200]
        title = p.get('title', '')[:100]
        text = title if title else content
        if not text:
            text = content[:80]
        if not text:
            text = '(无内容)'
        post_lines.append(
            f"{i+1}. [{p.get('clicks', 0)}阅/{p.get('comments', 0)}评] {text}"
        )

    user_prompt = f"分析以下{len(posts)}条股吧帖子的情绪：\n\n" + '\n'.join(post_lines)

    url = f"{DEEPSEEK_BASE}/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SOCIAL_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 3000
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
        resp = opener.open(req, timeout=90)
        result = json.loads(resp.read())

        if 'choices' not in result or len(result['choices']) == 0:
            return {'error': 'API returned no choices', 'raw': result}

        content = result['choices'][0]['message']['content']

        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                analysis_list = parsed
            elif isinstance(parsed, dict):
                # Try common wrapper keys
                for key in ['results', 'analysis', 'sentiments', 'data', 'items']:
                    if key in parsed and isinstance(parsed[key], list):
                        analysis_list = parsed[key]
                        break
                else:
                    return {'error': f'Unexpected dict format (keys: {list(parsed.keys())})', 'raw': content[:300]}
            else:
                return {'error': f'Unexpected type: {type(parsed)}', 'raw': content[:300]}
        except json.JSONDecodeError:
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                try:
                    analysis_list = json.loads(match.group())
                except json.JSONDecodeError:
                    return {'error': 'JSON parse failed', 'raw': content[:300]}
            else:
                return {'error': 'No JSON array found', 'raw': content[:300]}

        return {
            'results': analysis_list,
            'usage': result.get('usage', {}),
            'model': result.get('model', model),
        }

    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ''
        return {'error': f'HTTP {e.code}: {body[:500]}'}
    except Exception as e:
        return {'error': str(e)}


# ─── Main Analyzer ─────────────────────────────────────────

class SocialSentimentAnalyzer:
    """Analyze stock social sentiment from Guba posts."""

    def __init__(self, store: SocialSentimentStore = None, batch_size: int = BATCH_SIZE):
        self.store = store or SocialSentimentStore()
        self.batch_size = batch_size
        self._api_key = None

    @property
    def api_key(self):
        if self._api_key is None:
            self._api_key = _load_api_key()
        return self._api_key

    def analyze(self, code: str, pages: int = DEFAULT_PAGES,
                force_llm: bool = False, use_cache: bool = True) -> dict:
        """Run full social sentiment analysis for a stock."""
        posts = fetch_guba_posts(code, pages=pages)
        if not posts:
            return {
                'error': f'No posts found for {code}',
                'stock_code': code,
                'post_count': 0,
            }

        results = []
        api_calls = 0
        cache_hits = 0
        uncached_posts = []
        uncached_indices = []

        for i, post in enumerate(posts):
            pid = post['post_id']
            if use_cache and not force_llm:
                cached = self.store.get(pid)
                if cached:
                    results.append({**post, **cached, 'source': 'cache'})
                    cache_hits += 1
                    continue

            uncached_posts.append(post)
            uncached_indices.append(i)
            results.append(None)

        if uncached_posts and self.api_key:
            for batch_start in range(0, len(uncached_posts), self.batch_size):
                batch_end = min(batch_start + self.batch_size, len(uncached_posts))
                batch = uncached_posts[batch_start:batch_end]
                batch_indices = uncached_indices[batch_start:batch_end]

                llm_result = call_llm_social(batch, self.api_key)
                api_calls += 1

                if 'error' in llm_result:
                    for j, post in enumerate(batch):
                        idx = batch_indices[j]
                        results[idx] = {
                            **post,
                            'score': 0.0, 'label': 'neutral',
                            'confidence': 0.1,
                            'reasoning': f'LLM error: {llm_result["error"][:50]}',
                            'topics': [], 'influence': 'low', 'source': 'error',
                        }
                    continue

                analyses = llm_result.get('results', [])
                for analysis in analyses:
                    analysis_idx = analysis.get('index', 0) - 1
                    if 0 <= analysis_idx < len(batch):
                        post = batch[analysis_idx]
                        idx = batch_indices[analysis_idx]

                        entry = {
                            **post,
                            'score': float(analysis.get('score', 0)),
                            'label': analysis.get('label', 'neutral'),
                            'confidence': float(analysis.get('confidence', 0.5)),
                            'reasoning': analysis.get('reasoning', ''),
                            'topics': analysis.get('topics', []),
                            'influence': analysis.get('influence', 'low'),
                            'source': 'llm',
                            'model': llm_result.get('model', 'unknown'),
                        }
                        results[idx] = entry

                        self.store.put(post['post_id'], {
                            'score': entry['score'],
                            'label': entry['label'],
                            'confidence': entry['confidence'],
                            'reasoning': entry['reasoning'],
                            'topics': entry['topics'],
                            'influence': entry['influence'],
                            'model': entry['model'],
                            'analyzed_at': datetime.now().isoformat(),
                        })

                if batch_end < len(uncached_posts):
                    time.sleep(0.5)

        elif uncached_posts:
            for j, post in enumerate(uncached_posts):
                idx = uncached_indices[j]
                results[idx] = {
                    **post,
                    'score': 0.0, 'label': 'neutral',
                    'confidence': 0.0, 'reasoning': 'no_api_key',
                    'topics': [], 'influence': 'low', 'source': 'no_key',
                }

        scored = [r for r in results if r and r['source'] in ('llm', 'cache')]
        all_results = [r for r in results if r]

        return self._aggregate(code, all_results, scored, api_calls, cache_hits)

    def _aggregate(self, code: str, all_results: list, scored: list,
                   api_calls: int, cache_hits: int) -> dict:
        if not scored:
            return {
                'stock_code': code,
                'post_count': len(all_results),
                'scored_count': 0,
                'overall_score': 0.0,
                'overall_label': 'neutral',
                'overall_confidence': 0.0,
                'api_calls': api_calls,
                'cache_hits': cache_hits,
                'error': 'No posts could be scored',
                'posts': all_results,
                'themes': [],
            }

        total_weight = 0
        weighted_score = 0.0
        labels = {'bullish': 0, 'bearish': 0, 'neutral': 0}
        topic_counts = {}
        high_influence_posts = []

        for r in scored:
            engagement = r.get('clicks', 0) + r.get('comments', 0) * 5
            weight = max(1.0, math.log(engagement + 1))
            total_weight += weight
            weighted_score += r['score'] * weight

            labels[r.get('label', 'neutral')] = labels.get(r.get('label', 'neutral'), 0) + 1

            for topic in r.get('topics', []):
                topic = topic.strip()
                if topic:
                    topic_counts[topic] = topic_counts.get(topic, 0) + 1

            if r.get('influence') == 'high':
                high_influence_posts.append(r)
            elif r.get('is_hot') and len(high_influence_posts) < 20:
                high_influence_posts.append(r)

        overall_score = round(weighted_score / total_weight, 2) if total_weight > 0 else 0.0

        if overall_score > 0.15:
            overall_label = 'bullish'
        elif overall_score < -0.15:
            overall_label = 'bearish'
        else:
            overall_label = 'neutral'

        top_themes = sorted(topic_counts.items(), key=lambda x: -x[1])[:10]

        total_labeled = sum(labels.values())
        bull_ratio = labels['bullish'] / total_labeled if total_labeled > 0 else 0
        bear_ratio = labels['bearish'] / total_labeled if total_labeled > 0 else 0

        avg_confidence = round(
            sum(r.get('confidence', 0) for r in scored) / len(scored), 2
        ) if scored else 0.0

        return {
            'stock_code': code,
            'post_count': len(all_results),
            'scored_count': len(scored),
            'api_calls': api_calls,
            'cache_hits': cache_hits,
            'overall_score': overall_score,
            'overall_label': overall_label,
            'overall_confidence': avg_confidence,
            'bull_count': labels['bullish'],
            'bear_count': labels['bearish'],
            'neutral_count': labels['neutral'],
            'bull_ratio': round(bull_ratio, 2),
            'bear_ratio': round(bear_ratio, 2),
            'themes': top_themes,
            'high_influence': high_influence_posts[:5],
            'posts': all_results,
        }


# ─── Convenience Functions ─────────────────────────────────

_analyzer: Optional[SocialSentimentAnalyzer] = None


def analyze_social_sentiment(code: str, pages: int = DEFAULT_PAGES,
                              force_llm: bool = False) -> dict:
    """Convenience function — analyze social sentiment for a stock."""
    global _analyzer
    if _analyzer is None:
        _analyzer = SocialSentimentAnalyzer()
    return _analyzer.analyze(code, pages=pages, force_llm=force_llm)


def print_social_sentiment(result: dict):
    """Pretty-print social sentiment analysis results."""
    if 'error' in result:
        print(f"  Error: {result.get('error')}")
        return

    label_map = {'bullish': '📈 看多', 'bearish': '📉 看空', 'neutral': '➡️  中性'}
    influence_map = {'high': '🔥', 'medium': '📌', 'low': '  '}

    print(f"\n{'='*60}")
    print(f"  社交情绪分析 — {result.get('stock_code', '')}")
    print(f"{'='*60}")

    print(f"\n  📊 总览:")
    print(f"     情绪评分: {result['overall_score']:+.2f}  {label_map.get(result['overall_label'], result['overall_label'])}")
    print(f"     置信度:   {result.get('overall_confidence', 0):.2f}")
    print(f"     帖子总数: {result['post_count']}  (已评分: {result['scored_count']})")
    print(f"     看多: {result.get('bull_count', 0)} ({result.get('bull_ratio', 0):.0%})  "
          f"看空: {result.get('bear_count', 0)} ({result.get('bear_ratio', 0):.0%})  "
          f"中性: {result.get('neutral_count', 0)}")
    print(f"     API调用: {result.get('api_calls', 0)}  缓存命中: {result.get('cache_hits', 0)}")

    themes = result.get('themes', [])
    if themes:
        print(f"\n  💬 热门讨论主题:")
        for topic, count in themes:
            bar = '█' * min(count, 20)
            print(f"     {topic:<10} {bar} ({count})")

    high = result.get('high_influence', [])
    if high:
        print(f"\n  🔥 高影响力帖子:")
        for post in high[:5]:
            icon = influence_map.get(post.get('influence', 'low'), '  ')
            lbl = label_map.get(post.get('label', 'neutral'), '➡️')
            title = (post.get('title') or post.get('content', ''))[:60]
            print(f"     {icon} [{lbl}] {title}")
            if post.get('reasoning'):
                print(f"        理由: {post['reasoning'][:50]}")

    print(f"\n{'='*60}\n")


def print_store_stats():
    """Print social sentiment cache statistics."""
    store = SocialSentimentStore()
    stats = store.stats()
    print(f"\n  社交情绪缓存统计 (SocialSentimentStore):")
    print(f"    总缓存: {stats['total_cached']}")
    if stats['total_cached'] > 0:
        print(f"    看多: {stats['bullish']} ({stats['bullish']/stats['total_cached']:.0%})")
        print(f"    看空: {stats['bearish']} ({stats['bearish']/stats['total_cached']:.0%})")
        print(f"    中性: {stats['neutral']} ({stats['neutral']/stats['total_cached']:.0%})")
    print(f"    存储路径: {stats.get('store_path', SOCIAL_STORE_PATH)}\n")
