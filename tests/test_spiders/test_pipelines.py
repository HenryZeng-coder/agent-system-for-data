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

    def test_exclude_keyword_drop(self):
        """经营范围含排除词(贸易) → DropItem"""
        p = FilterPipeline()
        item = self._make_item(company_name="test", business_scope="五金贸易")
        try:
            p.process_item(item, None)
            assert False, "应该抛出 DropItem"
        except DropItem:
            assert True

    def test_medium_single_drop(self):
        """仅命中1个中词(无强词/弱词配合) → DropItem"""
        p = FilterPipeline()
        # "科技"在strong里, 用纯中词 "自动化" 测试
        item = self._make_item(company_name="test", business_scope="自动化设备")
        try:
            p.process_item(item, None)
            assert False, "应该抛出 DropItem"
        except DropItem:
            assert True

    def test_medium_double_pass(self):
        """命中2个中词 → 保留"""
        p = FilterPipeline()
        item = self._make_item(company_name="test", business_scope="自动化电子")
        assert p.process_item(item, None) is item

    def test_medium_plus_weak_pass(self):
        """命中1中词+1弱词 → 保留"""
        p = FilterPipeline()
        item = self._make_item(company_name="test", business_scope="自动化技术服务")
        assert p.process_item(item, None) is item

    def test_strong_plus_exclude_pass(self):
        """命中强词(软件)且含排除词 → 保留 (排除词不覆盖强词)"""
        p = FilterPipeline()
        item = self._make_item(company_name="test", business_scope="软件开发 物流")
        assert p.process_item(item, None) is item

    def test_config_loading(self):
        """配置文件加载: 词库数量大于内置回退"""
        p = FilterPipeline()
        assert len(p.keywords["strong"]) > 10


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
    """完整性 + 真实性验证管道"""

    def _make_item(self, **kwargs):
        item = CompanyItem()
        for k, v in kwargs.items():
            item[k] = v
        return item

    @staticmethod
    def _valid_credit_code(prefix="91420100MA4KTEST0"):
        """用 GB32100 校验和算法生成合法信用代码"""
        return prefix + ValidatePipeline.calculate_check_char(prefix)

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
        """credit_code 格式 + 校验和正确 → 保留"""
        p = ValidatePipeline()
        code = self._valid_credit_code()
        item = self._make_item(company_name="test", credit_code=code)
        result = p.process_item(item, None)
        assert result["credit_code"] == code

    def test_bad_checksum_credit_code_nullified(self):
        """credit_code 18位但校验和错误 → 置空"""
        p = ValidatePipeline()
        item = self._make_item(company_name="test", credit_code="91420100MA4KTEST00")
        result = p.process_item(item, None)
        assert result["credit_code"] is None

    def test_no_credit_code_pass(self):
        """无 credit_code → 不报错"""
        p = ValidatePipeline()
        item = self._make_item(company_name="test")
        result = p.process_item(item, None)
        assert result["company_name"] == "test"

    # ---- 真实性验证 ----

    def test_future_established_date_nullified(self):
        """成立日期晚于今天 → 置空"""
        p = ValidatePipeline()
        item = self._make_item(company_name="test", established_date="2099-01-01")
        result = p.process_item(item, None)
        assert result["established_date"] is None

    def test_valid_established_date_kept(self):
        """成立日期合理 → 保留"""
        p = ValidatePipeline()
        item = self._make_item(company_name="test", established_date="2015-06-01")
        result = p.process_item(item, None)
        assert result["established_date"] == "2015-06-01"

    def test_invalid_capital_nullified(self):
        """注册资本为负 → 置空"""
        p = ValidatePipeline()
        item = self._make_item(company_name="test", capital_amount=-500)
        result = p.process_item(item, None)
        assert result["capital_amount"] is None

    def test_oversize_capital_nullified(self):
        """注册资本超上限 → 置空"""
        p = ValidatePipeline()
        item = self._make_item(company_name="test", capital_amount=99_999_999_999)
        result = p.process_item(item, None)
        assert result["capital_amount"] is None

    def test_valid_capital_kept(self):
        """注册资本合理 → 保留"""
        p = ValidatePipeline()
        item = self._make_item(company_name="test", capital_amount=5000)
        result = p.process_item(item, None)
        assert result["capital_amount"] == 5000

    def test_noise_name_dropped(self):
        """名称含搜索噪声词且无公司后缀 → DropItem"""
        p = ValidatePipeline()
        item = self._make_item(company_name="搜索武汉AI结果")
        try:
            p.process_item(item, None)
            assert False, "应该抛出 DropItem"
        except DropItem:
            assert True

    def test_salary_min_max_valid(self):
        """薪资区间合理 → 保留"""
        from wuhan_it_crawler.items import RecruitmentItem
        p = ValidatePipeline()
        item = RecruitmentItem()
        item["company_id"] = 1
        item["position_title"] = "Python工程师"
        item["salary_min"] = 15000
        item["salary_max"] = 30000
        result = p.process_item(item, None)
        assert result["salary_min"] == 15000
        assert result["salary_max"] == 30000

    def test_salary_min_gt_max_nullified(self):
        """薪资 min > max → 置空"""
        from wuhan_it_crawler.items import RecruitmentItem
        p = ValidatePipeline()
        item = RecruitmentItem()
        item["company_id"] = 1
        item["position_title"] = "Java工程师"
        item["salary_min"] = 50000
        item["salary_max"] = 10000
        result = p.process_item(item, None)
        assert result["salary_min"] is None
        assert result["salary_max"] is None

    def test_news_future_date_nullified(self):
        """新闻发布日期晚于今天 → 置空"""
        from wuhan_it_crawler.items import NewsMentionItem
        p = ValidatePipeline()
        item = NewsMentionItem()
        item["company_id"] = 1
        item["title"] = "测试新闻"
        item["published_at"] = "2099-12-31"
        result = p.process_item(item, None)
        assert result["published_at"] is None

    def test_budget_negative_nullified(self):
        """招标预算为负 → 置空"""
        from wuhan_it_crawler.items import BiddingItem
        p = ValidatePipeline()
        item = BiddingItem()
        item["company_id"] = 1
        item["project_name"] = "测试项目"
        item["budget_amount"] = -100
        result = p.process_item(item, None)
        assert result["budget_amount"] is None

    # ---- GB 32100-2015 校验和算法 ----

    def test_calculate_check_char_deterministic(self):
        """同一前缀校验字符一致"""
        prefix = "91420100MA4KTEST0"
        assert ValidatePipeline.calculate_check_char(prefix) == \
            ValidatePipeline.calculate_check_char(prefix)

    def test_checksum_roundtrip(self):
        """生成代码必须通过校验"""
        code = self._valid_credit_code()
        assert ValidatePipeline.is_valid_credit_code(code)

    def test_checksum_rejects_tampered(self):
        """篡改校验位 → 校验失败"""
        code = self._valid_credit_code()
        tampered = code[:17] + ('0' if code[17] != '0' else '1')
        assert not ValidatePipeline.is_valid_credit_code(tampered)

    def test_checksum_rejects_short(self):
        """位数不足 → 校验失败"""
        assert not ValidatePipeline.is_valid_credit_code("91420100MA4KTEST0")

    def test_checksum_rejects_illegal_char(self):
        """含非法字符 → 校验失败"""
        assert not ValidatePipeline.is_valid_credit_code("91420100MA4KTEST0!")


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
