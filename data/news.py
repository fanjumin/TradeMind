"""
News fetching module for TradeMind.
Fetches stock-specific news from Sina Corp News and Sina Feed API.

Data sources:
  1. Sina Corp News — individual stock news with dates, titles, URLs
  2. Sina Feed — general financial news stream

No external dependencies beyond requests + stdlib.
"""

import requests
import re
import time
from datetime import datetime


# ─── Constants ────────────────────────────────────────────────────────────────

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ),
}

# Sina market prefix mapping
_SINA_PREFIX = {
    '6': 'sh',   # Shanghai
    '0': 'sz',   # Shenzhen main
    '3': 'sz',   # Shenzhen ChiNext
    '4': 'bj',   # Beijing
    '8': 'bj',   # Beijing
    '9': 'sh',   # Shanghai B-share
}


def _clean_symbol(symbol: str) -> str:
    """Strip .SH / .SZ / .BJ suffix, return pure 6-digit code."""
    return symbol.replace('.SH', '').replace('.SZ', '').replace('.BJ', '').strip()


def _sina_prefix(symbol: str) -> str:
    """Return sina market prefix (sh/sz/bj) for a stock code."""
    code = _clean_symbol(symbol)
    return _SINA_PREFIX.get(code[0], 'sz')


def get_stock_news(symbol: str, max_items: int = 20) -> list:
    """
    Fetch recent news for a single stock from Sina Corp News.

    Args:
        symbol: Stock code, e.g. '600519' or '600519.SH'
        max_items: Maximum number of news items to return (default 20)

    Returns:
        List of news dicts with keys: date, time, title, url, source
    """
    code = _clean_symbol(symbol)
    prefix = _sina_prefix(symbol)
    url = (
        'https://vip.stock.finance.sina.com.cn/corp/go.php/'
        f'vCB_AllNewsStock/symbol/{prefix}{code}.phtml'
    )

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        # Sina uses GBK encoding
        text = r.content.decode('gbk', errors='ignore')
    except requests.RequestException as e:
        return [{'error': f'Failed to fetch news: {e}'}]
    except UnicodeDecodeError:
        text = r.text

    # Parse news items: each item has date, time, link with title
    news_items = []

    # Pattern: date, time prefix, then <a href='...'>TITLE</a>
    pattern = re.compile(
        r'(\d{4}-\d{2}-\d{2})\D+?(\d{2}:\d{2})\D*?'
        r"<a[^>]*href='([^']*)'[^>]*>(.*?)</a>",
        re.DOTALL,
    )

    matches = pattern.findall(text)

    for date_str, time_str, href, title_raw in matches:
        # Clean HTML tags from title
        title = re.sub(r'<[^>]+>', '', title_raw).strip()
        title = re.sub(r'&nbsp;', ' ', title).strip()
        title = re.sub(r'\s+', ' ', title)

        if not title or len(title) < 5:
            continue

        # Determine source from URL domain
        source = '新浪财经'
        if 'cj.sina.cn' in href:
            source = '新浪财经'
        elif 'stock.finance.sina.com.cn' in href:
            source = '新浪证券'

        news_items.append({
            'date': date_str,
            'time': time_str,
            'title': title,
            'url': href,
            'source': source,
        })

        if len(news_items) >= max_items:
            break

    return news_items


def get_market_news(max_items: int = 15) -> list:
    """
    Fetch general financial market news from Sina Feed API.

    Args:
        max_items: Maximum number of news items (default 15)

    Returns:
        List of news dicts with keys: title, url, time, source, intro
    """
    url = (
        'https://feed.mix.sina.com.cn/api/roll/get'
        '?pageid=153&lid=2509&k=&num={}'.format(min(max_items, 50))
    )

    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        return [{'error': f'Failed to fetch market news: {e}'}]

    results = []
    entries = data.get('result', {}).get('data', [])

    for item in entries[:max_items]:
        ctime = item.get('ctime', '')
        # Convert Unix timestamp to date string
        try:
            ts = int(ctime)
            dt = datetime.fromtimestamp(ts)
            date_str = dt.strftime('%Y-%m-%d')
            time_str = dt.strftime('%H:%M')
        except (ValueError, TypeError):
            date_str = ''
            time_str = ''

        results.append({
            'date': date_str,
            'time': time_str,
            'title': item.get('title', ''),
            'url': item.get('url', ''),
            'source': item.get('media_name', '新浪财经'),
            'intro': item.get('intro', ''),
        })

    return results


def get_news_summary(symbol: str) -> dict:
    """
    Get combined news summary for a stock: recent news + relevant market news.

    Args:
        symbol: Stock code, e.g. '600519'

    Returns:
        dict with keys: stock_news (list), market_news (list), count, fetched_at
    """
    stock_news = get_stock_news(symbol, max_items=20)

    # Also fetch market news for broader context
    market_news = get_market_news(max_items=10)

    return {
        'symbol': _clean_symbol(symbol),
        'stock_news': stock_news,
        'market_news': market_news,
        'count': len(stock_news),
        'fetched_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
