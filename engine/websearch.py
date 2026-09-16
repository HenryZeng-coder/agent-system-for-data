"""WebSearch 聚合引擎 — 百度/搜狗/必应/360/头条

五引擎并行搜索，单引擎失败自动降级，URL去重+相关度排序。
"""

import re
import logging
from urllib.parse import quote_plus, urljoin, unquote, urlparse, parse_qs
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class WebSearchEngine:
    """多搜索引擎聚合"""

    # 搜索引擎 URL 模板
    BAIDU_URL = 'https://www.baidu.com/s'
    SOGOU_URL = 'https://www.sogou.com/web'
    BING_URL = 'https://www.bing.com/search'
    SO360_URL = 'https://www.so.com/s'          # 360搜索
    TOUTIAO_URL = 'https://so.toutiao.com/search'  # 头条搜索

    # 请求超时和重试
    TIMEOUT = 15
    MAX_RETRIES = 2

    # UA 池
    USER_AGENTS = [
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    ]

    def __init__(self):
        self.engines = {
            "baidu": self._search_baidu,
            "sogou": self._search_sogou,
            "bing": self._search_bing,
            "so360": self._search_so360,
            "toutiao": self._search_toutiao,
        }

    def search(self, query: str, limit: int = 20) -> list:
        """聚合搜索: 五引擎并行，失败降级"""
        all_results = []
        per_engine_limit = limit // len(self.engines) + 2

        for name, engine_fn in self.engines.items():
            try:
                results = engine_fn(query, per_engine_limit)
                all_results.extend(results)
                logger.debug(f"搜索引擎 {name} 返回 {len(results)} 条")
            except Exception as e:
                logger.warning(f"搜索引擎 {name} 失败，降级: {e}")

        deduped = self._deduplicate(all_results)
        ranked = self._rank_by_relevance(deduped, query)
        return ranked[:limit]

    # ================================================================
    # 百度搜索
    # ================================================================

    def _search_baidu(self, query: str, limit: int) -> list:
        """百度网页搜索"""
        results = []
        headers = self._random_headers()

        try:
            resp = requests.get(
                f'{self.BAIDU_URL}?wd={quote_plus(query)}&rn={min(limit, 50)}',
                headers=headers,
                timeout=self.TIMEOUT,
            )
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, 'html.parser')

            # 百度搜索结果
            for item in soup.select('div.result, div.c-container'):
                title_el = item.select_one('h3 a, .t a')
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                url = title_el.get('href', '')

                # 百度链接需要解析真实URL
                if url.startswith('/link') or 'baidu.com' in url:
                    try:
                        real_resp = requests.get(url, headers=headers, timeout=5, allow_redirects=True)
                        url = real_resp.url
                    except Exception:
                        pass

                summary_el = item.select_one('.c-abstract, .content-right_8Zs40, span.content-right_8Zs40')
                summary = summary_el.get_text(strip=True) if summary_el else ''

                if title:
                    results.append({
                        'title': title,
                        'url': url,
                        'summary': summary,
                        'source': 'baidu',
                    })

        except requests.RequestException as e:
            logger.warning(f"百度搜索请求失败: {e}")
            raise

        return results[:limit]

    # ================================================================
    # 搜狗搜索
    # ================================================================

    def _search_sogou(self, query: str, limit: int) -> list:
        """搜狗网页搜索"""
        results = []
        headers = self._random_headers()

        try:
            resp = requests.get(
                f'{self.SOGOU_URL}?query={quote_plus(query)}&num={min(limit, 50)}',
                headers=headers,
                timeout=self.TIMEOUT,
            )
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, 'html.parser')

            for item in soup.select('div.vrwrap, div.rb, div.result'):
                title_el = item.select_one('h3 a, a[href]')
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                url = title_el.get('href', '')
                if url and not url.startswith('http'):
                    url = urljoin('https://www.sogou.com', url)

                summary_el = item.select_one('.str_text, .str_time-info, p')
                summary = summary_el.get_text(strip=True) if summary_el else ''

                if title:
                    results.append({
                        'title': title,
                        'url': url,
                        'summary': summary,
                        'source': 'sogou',
                    })

        except requests.RequestException as e:
            logger.warning(f"搜狗搜索请求失败: {e}")
            raise

        return results[:limit]

    # ================================================================
    # 必应搜索
    # ================================================================

    def _search_bing(self, query: str, limit: int) -> list:
        """必应网页搜索"""
        results = []
        headers = self._random_headers()

        try:
            resp = requests.get(
                f'{self.BING_URL}?q={quote_plus(query)}&count={min(limit, 50)}',
                headers=headers,
                timeout=self.TIMEOUT,
            )
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, 'html.parser')

            for item in soup.select('li.b_algo, div.b_algo'):
                title_el = item.select_one('h2 a, h3 a')
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                url = title_el.get('href', '')

                summary_el = item.select_one('.b_caption p, p')
                summary = summary_el.get_text(strip=True) if summary_el else ''

                if title:
                    results.append({
                        'title': title,
                        'url': url,
                        'summary': summary,
                        'source': 'bing',
                    })

        except requests.RequestException as e:
            logger.warning(f"必应搜索请求失败: {e}")
            raise

        return results[:limit]

    # ================================================================
    # 360搜索
    # ================================================================

    def _search_so360(self, query: str, limit: int) -> list:
        """360搜索 (so.com) — 国内份额第三，对中文站点覆盖好"""
        results = []
        headers = self._random_headers()

        try:
            resp = requests.get(
                f'{self.SO360_URL}?q={quote_plus(query)}&pn=1',
                headers=headers,
                timeout=self.TIMEOUT,
            )
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, 'html.parser')

            # 360搜索结果: li.res-list / div.res-list
            for item in soup.select('li.res-list, div.res-list, li[class*="result"]'):
                title_el = item.select_one('h3 a, h3.title a')
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                url = title_el.get('href', '')

                summary_el = item.select_one('.res-desc, .res-rich, p')
                summary = summary_el.get_text(strip=True) if summary_el else ''

                if title:
                    results.append({
                        'title': title,
                        'url': url,
                        'summary': summary,
                        'source': 'so360',
                    })

        except requests.RequestException as e:
            logger.warning(f"360搜索请求失败: {e}")
            raise

        return results[:limit]

    # ================================================================
    # 头条搜索
    # ================================================================

    def _search_toutiao(self, query: str, limit: int) -> list:
        """头条搜索 (so.toutiao.com) — 资讯/自媒体内容覆盖好"""
        results = []
        headers = self._random_headers()

        try:
            resp = requests.get(
                f'{self.TOUTIAO_URL}?dvpf=pc&source=input&keyword={quote_plus(query)}',
                headers=headers,
                timeout=self.TIMEOUT,
            )
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, 'html.parser')

            # 头条搜索: 结果条目 a[href*="search/jump"] 为跳转链接, 内含真实URL
            skip_titles = {'去西瓜搜', '去抖音搜', '查看更多', '下一页', '换一换',
                           '搜索热词', '大家都在搜', '无障碍'}
            for item in soup.select('a[href*="search/jump"]'):
                title = item.get_text(strip=True)
                if not title or len(title) < 4 or title in skip_titles:
                    continue
                jump_url = str(item.get('href', '') or '')
                real_url = self._resolve_jump_url(jump_url)
                if not real_url:
                    continue

                # 摘要: 取父容器内 p 文本
                summary = ''
                container = item.find_parent('div')
                if container:
                    p_el = container.select_one('p, .summary, .desc')
                    if p_el:
                        summary = p_el.get_text(strip=True)

                results.append({
                    'title': title,
                    'url': real_url,
                    'summary': summary,
                    'source': 'toutiao',
                })

        except requests.RequestException as e:
            logger.warning(f"头条搜索请求失败: {e}")
            raise

        return results[:limit]

    @staticmethod
    def _resolve_jump_url(jump_url: str) -> str:
        """解析头条跳转链接 → 真实URL"""
        try:
            parsed = urlparse(jump_url)
            params = parse_qs(parsed.query)
            real = params.get('url', [''])[0]
            if real:
                return unquote(real)
        except Exception:
            pass
        return ''

    # ================================================================
    # 去重与排序
    # ================================================================

    def _deduplicate(self, results: list) -> list:
        """URL 去重"""
        seen_urls = set()
        seen_titles = set()
        unique = []

        for r in results:
            url = r.get("url", "")
            title = r.get("title", "").strip()

            # URL 去重
            if url in seen_urls:
                continue
            # 标题去重 (相似标题)
            normalized_title = re.sub(r'\s+', '', title.lower())
            if normalized_title in seen_titles:
                continue

            seen_urls.add(url)
            seen_titles.add(normalized_title)
            unique.append(r)

        return unique

    def _rank_by_relevance(self, results: list, query: str) -> list:
        """按相关度排序"""
        query_terms = query.lower().split()

        for r in results:
            score = 0.0
            text = f'{r.get("title", "")} {r.get("summary", "")}'.lower()
            for term in query_terms:
                if term in text:
                    score += 1.0
            r['relevance_score'] = score

        results.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        return results

    # ================================================================
    # 工具方法
    # ================================================================

    def _random_headers(self) -> dict:
        """生成随机请求头"""
        import random
        return {
            'User-Agent': random.choice(self.USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
