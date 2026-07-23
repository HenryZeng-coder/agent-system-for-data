"""WebSearch 聚合引擎 — 百度/搜狗/必应"""

import logging

logger = logging.getLogger(__name__)


class WebSearchEngine:
    """多搜索引擎聚合"""

    def __init__(self):
        self.engines = {
            "baidu": self._search_baidu,
            "sogou": self._search_sogou,
            "bing": self._search_bing,
        }

    def search(self, query: str, limit: int = 10) -> list:
        all_results = []
        for name, engine_fn in self.engines.items():
            try:
                results = engine_fn(query, limit // len(self.engines) + 1)
                all_results.extend(results)
            except Exception as e:
                logger.warning(f"搜索引擎 {name} 失败: {e}")
        return self._deduplicate(all_results)[:limit]

    def _search_baidu(self, query: str, limit: int) -> list:
        # TODO: 实现百度搜索
        return []

    def _search_sogou(self, query: str, limit: int) -> list:
        # TODO: 实现搜狗搜索
        return []

    def _search_bing(self, query: str, limit: int) -> list:
        # TODO: 实现必应搜索
        return []

    def _deduplicate(self, results: list) -> list:
        seen_urls = set()
        unique = []
        for r in results:
            url = r.get("url", "")
            if url not in seen_urls:
                seen_urls.add(url)
                unique.append(r)
        return unique
