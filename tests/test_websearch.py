"""WebSearchEngine 单元测试 — 引擎注册/跳转解析/去重排序 (无网络)"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.websearch import WebSearchEngine


class TestEngineRegistry:
    """五引擎注册验证"""

    def test_five_engines_registered(self):
        e = WebSearchEngine()
        assert set(e.engines.keys()) == {"baidu", "sogou", "bing", "so360", "toutiao"}

    def test_engine_methods_callable(self):
        e = WebSearchEngine()
        for name, fn in e.engines.items():
            assert callable(fn), f"引擎 {name} 不可调用"


class TestJumpUrlResolution:
    """头条跳转链接解析"""

    def test_resolve_jump_url(self):
        jump = "https://sou.toutiao.com/search/jump?url=https%3A%2F%2Fwww.toutiao.com%2Farticle%2F123"
        assert WebSearchEngine._resolve_jump_url(jump) == \
            "https://www.toutiao.com/article/123"

    def test_resolve_jump_url_empty(self):
        assert WebSearchEngine._resolve_jump_url("") == ""

    def test_resolve_jump_url_no_param(self):
        assert WebSearchEngine._resolve_jump_url("https://sou.toutiao.com/search") == ""


class TestDedupAndRank:
    """去重与排序逻辑"""

    def _make_results(self):
        return [
            {"title": "武汉AI公司", "url": "http://a.com/1", "summary": "", "source": "baidu"},
            {"title": "武汉AI公司", "url": "http://a.com/1", "summary": "", "source": "sogou"},  # 同URL
            {"title": "武汉AI公司", "url": "http://b.com/2", "summary": "", "source": "bing"},   # 同标题
            {"title": "武汉AI招聘", "url": "http://c.com/3", "summary": "招聘", "source": "so360"},
        ]

    def test_deduplicate_by_url_and_title(self):
        e = WebSearchEngine()
        unique = e._deduplicate(self._make_results())
        assert len(unique) == 2

    def test_rank_by_relevance(self):
        e = WebSearchEngine()
        results = [
            {"title": "无关内容", "url": "http://a.com/1", "summary": "", "source": "baidu"},
            {"title": "武汉 AI 公司 招聘", "url": "http://b.com/2", "summary": "武汉 AI", "source": "so360"},
        ]
        ranked = e._rank_by_relevance(results, "武汉 AI 公司")
        # 相关度高的排前面
        assert ranked[0]["title"] == "武汉 AI 公司 招聘"
