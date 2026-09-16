"""NewsSpider 等级筛选 (levels) 离线测试

只测试参数解析, 不连数据库、不发网络请求。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "crawler"))

from cn_it_crawler.spiders.news_spider import NewsSpider


class TestNewsSpiderLevels:
    """验证 -a levels=S,A 参数能被正确解析 (修复前该参数被 **kwargs 静默忽略)"""

    def test_none_and_empty(self):
        assert NewsSpider._parse_levels(None) == []
        assert NewsSpider._parse_levels("") == []
        assert NewsSpider._parse_levels([]) == []

    def test_single(self):
        assert NewsSpider._parse_levels("S") == ["S"]

    def test_multiple_sorted(self):
        # 传入顺序无关, 返回值固定按 S>A>B>C>D
        assert NewsSpider._parse_levels("A,S") == ["S", "A"]

    def test_lowercase_and_spaces(self):
        assert NewsSpider._parse_levels(" s , a ") == ["S", "A"]

    def test_fullwidth_comma(self):
        assert NewsSpider._parse_levels("S，A") == ["S", "A"]

    def test_invalid_dropped(self):
        assert NewsSpider._parse_levels("S,X") == ["S"]
        assert NewsSpider._parse_levels("X") == []

    def test_list_input(self):
        assert NewsSpider._parse_levels(["S", "A"]) == ["S", "A"]

    def test_accepts_levels_kwarg(self):
        """Scrapy 的 -a levels=S,A 应作为 levels 参数被接受而非落入 **kwargs"""
        import inspect

        params = inspect.signature(NewsSpider.__init__).parameters
        assert "levels" in params
