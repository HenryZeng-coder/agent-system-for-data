"""数据管道单元测试 — 5级处理: 去重/过滤/清洗/验证/标准化

覆盖:
- deduplicate: 基于credit_code去重，空值保留，完全重复
- filter_by_industry: IT关键词匹配/不匹配/边界
- clean_fields: HTML清除/全角转换/空值/空白压缩
- validate_completeness: company_name必填/credit_code格式
- standardize: 注册资本解析/日期标准化
- run: 全流程5级管道
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.data_pipeline import DataPipeline


class TestDeduplicate:
    """去重管道测试"""

    def test_dedup(self):
        """基本去重: 3条含2条重复 → 2条"""
        p = DataPipeline()
        d = [{"credit_code": "A"}, {"credit_code": "A"}, {"credit_code": "B"}]
        assert len(p.deduplicate(d)) == 2

    def test_dedup_empty(self):
        """空列表 → 空列表"""
        p = DataPipeline()
        assert p.deduplicate([]) == []

    def test_dedup_all_unique(self):
        """全部唯一 → 不变"""
        p = DataPipeline()
        d = [{"credit_code": "A"}, {"credit_code": "B"}, {"credit_code": "C"}]
        assert len(p.deduplicate(d)) == 3

    def test_dedup_all_same(self):
        """全部重复 → 仅1条"""
        p = DataPipeline()
        d = [{"credit_code": "X"}] * 5
        assert len(p.deduplicate(d)) == 1

    def test_dedup_none_credit_code(self):
        """无 credit_code 的记录保留"""
        p = DataPipeline()
        d = [{"credit_code": None, "name": "a"}, {"credit_code": None, "name": "b"}]
        result = p.deduplicate(d)
        assert len(result) == 2

    def test_dedup_preserves_order(self):
        """去重保留首次出现顺序"""
        p = DataPipeline()
        d = [{"credit_code": "B"}, {"credit_code": "A"}, {"credit_code": "B"}]
        result = p.deduplicate(d)
        assert [r["credit_code"] for r in result] == ["B", "A"]


class TestFilterByIndustry:
    """IT行业过滤测试"""

    def test_filter_match(self):
        """匹配IT关键词 → 保留"""
        p = DataPipeline()
        d = [{"business_scope": "人工智能软件开发"}]
        assert len(p.filter_by_industry(d)) == 1

    def test_filter_no_match(self):
        """不匹配IT关键词 → 过滤掉"""
        p = DataPipeline()
        d = [{"business_scope": "五金加工维修"}]
        assert len(p.filter_by_industry(d)) == 0

    def test_filter_mixed(self):
        """混合: 1匹配1不匹配 → 保留1条"""
        p = DataPipeline()
        d = [
            {"business_scope": "人工智能软件开发"},
            {"business_scope": "五金加工"},
        ]
        result = p.filter_by_industry(d)
        assert len(result) == 1
        assert result[0]["business_scope"] == "人工智能软件开发"

    def test_filter_industry_tags(self):
        """industry_tags 列表也能匹配"""
        p = DataPipeline()
        d = [{"business_scope": "", "industry_tags": ["云计算"]}]
        assert len(p.filter_by_industry(d)) == 1

    def test_filter_multiple_keywords(self):
        """多个IT关键词匹配 → 保留"""
        p = DataPipeline()
        d = [{"business_scope": "大数据分析、数字化平台"}]
        assert len(p.filter_by_industry(d)) == 1

    def test_filter_empty_scope(self):
        """business_scope 为空 + 无 tags → 过滤掉"""
        p = DataPipeline()
        d = [{"business_scope": ""}]
        assert len(p.filter_by_industry(d)) == 0


class TestCleanFields:
    """数据清洗测试"""

    def test_clean_html(self):
        """清除 HTML 标签"""
        p = DataPipeline()
        d = [{"name": "<b>武汉</b>科技"}]
        result = p.clean_fields(d)
        assert result[0]["name"] == "武汉科技"

    def test_clean_whitespace(self):
        """压缩多余空白"""
        p = DataPipeline()
        d = [{"scope": "  人工  智能  "}]
        result = p.clean_fields(d)
        assert result[0]["scope"] == "人工 智能"

    def test_clean_fullwidth(self):
        """全角数字转半角"""
        p = DataPipeline()
        d = [{"code": "０１２３"}]
        result = p.clean_fields(d)
        assert result[0]["code"] == "0123"

    def test_clean_null_values(self):
        """None 和空字符串 → 统一为 None"""
        p = DataPipeline()
        d = [{"name": None, "scope": ""}]
        result = p.clean_fields(d)
        assert result[0]["name"] is None
        assert result[0]["scope"] is None

    def test_clean_preserves_non_string(self):
        """非字符串值保持不变"""
        p = DataPipeline()
        d = [{"amount": 5000, "ratio": 0.35}]
        result = p.clean_fields(d)
        assert result[0]["amount"] == 5000
        assert result[0]["ratio"] == 0.35

    def test_clean_empty_string_becomes_none(self):
        """仅含空白 → None"""
        p = DataPipeline()
        d = [{"name": "   "}]
        result = p.clean_fields(d)
        assert result[0]["name"] is None


class TestValidateCompleteness:
    """完整性验证测试"""

    def test_validate_valid(self):
        """company_name 非空 → 保留"""
        p = DataPipeline()
        d = [{"company_name": "武汉AI"}]
        assert len(p.validate_completeness(d)) == 1

    def test_validate_missing_name(self):
        """company_name 为空 → 跳过"""
        p = DataPipeline()
        d = [{"company_name": None}]
        assert len(p.validate_completeness(d)) == 0

    def test_validate_empty_name(self):
        """company_name 为空字符串 → 跳过"""
        p = DataPipeline()
        d = [{"company_name": ""}]
        assert len(p.validate_completeness(d)) == 0

    def test_validate_credit_code_format(self):
        """credit_code 格式不对 → 置空 (不丢弃)"""
        p = DataPipeline()
        d = [{"company_name": "test", "credit_code": "SHORT"}]
        result = p.validate_completeness(d)
        assert len(result) == 1
        assert result[0]["credit_code"] is None

    def test_validate_credit_code_valid(self):
        """credit_code 18位格式正确 → 保留"""
        p = DataPipeline()
        d = [{"company_name": "test", "credit_code": "91420100MA4KTEST01"}]
        result = p.validate_completeness(d)
        assert len(result) == 1
        assert result[0]["credit_code"] == "91420100MA4KTEST01"

    def test_validate_mixed(self):
        """混合: 有名 + 无名 → 仅保留有名的"""
        p = DataPipeline()
        d = [{"company_name": "武汉AI"}, {"company_name": None}]
        assert len(p.validate_completeness(d)) == 1


class TestStandardize:
    """格式标准化测试"""

    def test_standardize_capital_wan(self):
        """注册资本: "5000万元" → 5000"""
        p = DataPipeline()
        d = [{"capital_amount": "5000万元"}]
        result = p.standardize(d)
        assert result[0]["capital_amount"] == 5000.0

    def test_standardize_capital_yi(self):
        """注册资本: "1亿" → 10000"""
        p = DataPipeline()
        d = [{"capital_amount": "1亿"}]
        result = p.standardize(d)
        assert result[0]["capital_amount"] == 10000.0

    def test_standardize_capital_number(self):
        """注册资本: 纯数值 → 保持"""
        p = DataPipeline()
        d = [{"capital_amount": 3000}]
        result = p.standardize(d)
        assert result[0]["capital_amount"] == 3000

    def test_standardize_registered_capital(self):
        """registered_capital 字段也能解析"""
        p = DataPipeline()
        d = [{"registered_capital": "2000万元"}]
        result = p.standardize(d)
        assert result[0]["capital_amount"] == 2000.0

    def test_standardize_date(self):
        """日期标准化: 2024年1月15日 → 2024-01-15"""
        p = DataPipeline()
        d = [{"established_date": "2024年1月15日"}]
        result = p.standardize(d)
        assert result[0]["established_date"] == "2024-01-15"

    def test_standardize_date_slash(self):
        """日期标准化: 2024/03/08 → 2024-03-08"""
        p = DataPipeline()
        d = [{"established_date": "2024/03/08"}]
        result = p.standardize(d)
        assert result[0]["established_date"] == "2024-03-08"


class TestRunFullPipeline:
    """5级管道全流程测试"""

    def test_run_empty(self):
        """空数据 → 空结果"""
        assert DataPipeline().run([]) == []

    def test_run_full(self):
        """完整5级管道: 去重→过滤→清洗→验证→标准化"""
        p = DataPipeline()
        d = [
            {
                "company_name": "武汉AI科技有限公司",
                "credit_code": "91420100MA4K00001",
                "business_scope": "人工智能软件开发、云计算",
                "capital_amount": "5000万元",
                "industry_tags": "科技",
            },
            {
                "company_name": "武汉AI科技有限公司",  # 重复 credit_code
                "credit_code": "91420100MA4K00001",
                "business_scope": "人工智能软件开发",
                "capital_amount": "5000万元",
            },
            {
                "company_name": "五金加工厂",  # 非IT行业 → 被过滤
                "credit_code": "91420100MA4K00002",
                "business_scope": "五金加工维修",
                "capital_amount": "100万",
            },
            {
                "company_name": None,  # 无名称 → 被验证剔除
                "credit_code": "91420100MA4K00003",
                "business_scope": "大数据分析",
            },
        ]
        result = p.run(d)
        # 去重: 4→3, 过滤: 3→2, 验证: 2→1 (去掉无名)
        assert len(result) == 1
        assert result[0]["company_name"] == "武汉AI科技有限公司"
        assert result[0]["capital_amount"] == 5000.0
