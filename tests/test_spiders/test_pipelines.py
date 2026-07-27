"""Scrapy 5级 Pipeline 离线测试

- FilterPipeline / CleanPipeline / ValidatePipeline: 直接实例化测试
- DedupPipeline / StandardizePipeline: 需要 DB，仅测试纯逻辑方法
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "crawler"))

from scrapy.exceptions import DropItem

from wuhan_it_crawler.pipelines.filter_pipeline import FilterPipeline
from wuhan_it_crawler.pipelines.clean_pipeline import CleanPipeline
from wuhan_it_crawler.pipelines.validate_pipeline import ValidatePipeline
from wuhan_it_crawler.pipelines.standardize_pipeline import StandardizePipeline
from wuhan_it_crawler.items import CompanyItem


# ================================================================
# FilterPipeline (无DB依赖)
# ================================================================

class TestFilterPipeline:
    """IT行业过滤管道"""

    def _make_item(self, **kwargs):
        item = CompanyItem()
        for k, v in kwargs.items():
            item[k] = v
        return item

    def test_it_scope_pass(self):
        """business_scope 含IT关键词 → 保留"""
        p = FilterPipeline()
        item = self._make_item(company_name="test", business_scope="人工智能软件开发")
        assert p.process_item(item, None) is item

    def test_non_it_scope_drop(self):
        """business_scope 不含IT关键词 → DropItem"""
        p = FilterPipeline()
        item = self._make_item(company_name="test", business_scope="五金加工维修")
        try:
            p.process_item(item, None)
            assert False, "应该抛出 DropItem"
        except DropItem:
            assert True

    def test_industry_tags_pass(self):
        """industry_tags 含IT关键词 → 保留"""
        p = FilterPipeline()
        item = self._make_item(company_name="test", business_scope="", industry_tags=["云计算"])
        assert p.process_item(item, None) is item

    def test_mixed_pass(self):
        """多关键词中有一个匹配 → 保留"""
        p = FilterPipeline()
        item = self._make_item(company_name="test", business_scope="大数据分析平台")
        assert p.process_item(item, None) is item

    def test_empty_scope_drop(self):
        """空 business_scope + 无 tags → DropItem"""
        p = FilterPipeline()
        item = self._make_item(company_name="test", business_scope="")
        try:
            p.process_item(item, None)
            assert False, "应该抛出 DropItem"
        except DropItem:
            assert True


# ================================================================
# CleanPipeline (无DB依赖)
# ================================================================

class TestCleanPipeline:
    """数据清洗管道"""

    def _make_item(self, **kwargs):
        item = CompanyItem()
        for k, v in kwargs.items():
            item[k] = v
        return item

    def test_html_removal(self):
        """清除 HTML 标签"""
        p = CleanPipeline()
        item = self._make_item(company_name="<b>武汉</b>科技")
        result = p.process_item(item, None)
        assert result["company_name"] == "武汉科技"

    def test_whitespace_compression(self):
        """压缩多余空白"""
        p = CleanPipeline()
        item = self._make_item(company_name="武汉  科技  公司")
        result = p.process_item(item, None)
        assert result["company_name"] == "武汉 科技 公司"

    def test_fullwidth_conversion(self):
        """全角标点转半角"""
        p = CleanPipeline()
        item = self._make_item(business_scope="软件开发（AI）")
        result = p.process_item(item, None)
        assert "(" in result["business_scope"]
        assert ")" in result["business_scope"]

    def test_null_string_to_none(self):
        """空字符串 → None"""
        p = CleanPipeline()
        item = self._make_item(company_name="test", business_scope="")
        result = p.process_item(item, None)
        assert result["business_scope"] is None

    def test_null_literal_to_none(self):
        """字符串 'null' → None"""
        p = CleanPipeline()
        item = self._make_item(company_name="test", business_scope="null")
        result = p.process_item(item, None)
        assert result["business_scope"] is None

    def test_numeric_preserved(self):
        """数值型字段不被清洗"""
        p = CleanPipeline()
        item = self._make_item(company_name="test", capital_amount=5000)
        result = p.process_item(item, None)
        assert result["capital_amount"] == 5000


# ================================================================
# ValidatePipeline (无DB依赖)
# ================================================================

class TestValidatePipeline:
    """完整性验证管道"""

    def _make_item(self, **kwargs):
        item = CompanyItem()
        for k, v in kwargs.items():
            item[k] = v
        return item

    def test_valid_item_pass(self):
        """company_name 非空 → 保留"""
        p = ValidatePipeline()
        item = self._make_item(company_name="武汉AI", credit_code="91420100MA4K00001")
        assert p.process_item(item, None) is item

    def test_missing_name_drop(self):
        """company_name 为空 → DropItem"""
        p = ValidatePipeline()
        item = self._make_item(company_name=None)
        try:
            p.process_item(item, None)
            assert False, "应该抛出 DropItem"
        except DropItem:
            assert True

    def test_empty_name_drop(self):
        """company_name 为空字符串 → DropItem"""
        p = ValidatePipeline()
        item = self._make_item(company_name="")
        try:
            p.process_item(item, None)
            assert False, "应该抛出 DropItem"
        except DropItem:
            assert True

    def test_bad_credit_code_nullified(self):
        """credit_code 格式不对 → 置空但不丢弃"""
        p = ValidatePipeline()
        item = self._make_item(company_name="test", credit_code="SHORT")
        result = p.process_item(item, None)
        assert result["credit_code"] is None

    def test_valid_credit_code_kept(self):
        """credit_code 格式正确 → 保留"""
        p = ValidatePipeline()
        item = self._make_item(company_name="test", credit_code="91420100MA4KTEST01")
        result = p.process_item(item, None)
        assert result["credit_code"] == "91420100MA4KTEST01"

    def test_no_credit_code_pass(self):
        """无 credit_code → 不报错"""
        p = ValidatePipeline()
        item = self._make_item(company_name="test")
        result = p.process_item(item, None)
        assert result["company_name"] == "test"


# ================================================================
# StandardizePipeline (仅测试纯逻辑方法, 无DB)
# ================================================================

class TestStandardizePipelineLogic:
    """StandardizePipeline 格式标准化逻辑 (无需DB)"""

    def test_parse_capital_wan(self):
        """5000万元 → 5000"""
        assert StandardizePipeline._parse_capital("5000万元") == 5000.0

    def test_parse_capital_yi(self):
        """1亿 → 10000"""
        assert StandardizePipeline._parse_capital("1亿") == 10000.0

    def test_parse_capital_2yi(self):
        """2.5亿 → 25000"""
        assert StandardizePipeline._parse_capital("2.5亿") == 25000.0

    def test_parse_capital_wan_only(self):
        """300万 (无"元") → 300"""
        assert StandardizePipeline._parse_capital("300万") == 300.0

    def test_parse_capital_pure_number(self):
        """5000 (纯数字, 无万/亿) → 0.5 (除以10000)"""
        result = StandardizePipeline._parse_capital("5000")
        assert result == 0.5

    def test_parse_capital_none(self):
        """None → None"""
        assert StandardizePipeline._parse_capital(None) is None

    def test_parse_capital_empty(self):
        """空字符串 → None"""
        assert StandardizePipeline._parse_capital("") is None

    def test_parse_date_chinese(self):
        """2020年1月15日 → 2020-01-15"""
        assert StandardizePipeline._parse_date("2020年1月15日") == "2020-01-15"

    def test_parse_date_dash(self):
        """2020-01-15 → 不变"""
        assert StandardizePipeline._parse_date("2020-01-15") == "2020-01-15"

    def test_parse_date_slash(self):
        """2020/01/15 → 2020-01-15"""
        assert StandardizePipeline._parse_date("2020/01/15") == "2020-01-15"

    def test_parse_date_dot(self):
        """2020.01.15 → 2020-01-15"""
        assert StandardizePipeline._parse_date("2020.01.15") == "2020-01-15"

    def test_parse_date_none(self):
        """None → None"""
        assert StandardizePipeline._parse_date(None) is None

    def test_parse_date_empty(self):
        """空字符串 → None"""
        assert StandardizePipeline._parse_date("") is None

    def test_parse_date_unparseable(self):
        """无法解析 → 原文返回"""
        assert StandardizePipeline._parse_date("最近") == "最近"
