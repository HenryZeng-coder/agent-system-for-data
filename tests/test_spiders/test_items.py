"""Scrapy Item 字段验证 — 确保每个 Item 定义与数据库表对齐"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "crawler"))

from wuhan_it_crawler.items import (
    CompanyItem, TechProfileItem, RecruitmentItem,
    NewsMentionItem, BiddingItem, CrawlTaskItem,
)


class TestCompanyItem:
    """企业主表 Item 验证"""

    def test_required_fields(self):
        item = CompanyItem()
        required = [
            "company_name", "credit_code", "registered_capital",
            "capital_amount", "established_date", "legal_representative",
            "business_scope", "registered_address", "status",
            "industry_tags", "source_url",
        ]
        for field in required:
            assert field in item.fields, f"CompanyItem 缺少字段: {field}"

    def test_can_set_values(self):
        item = CompanyItem()
        item["company_name"] = "武汉AI科技"
        item["credit_code"] = "91420100MA4K00001"
        assert item["company_name"] == "武汉AI科技"
        assert item["credit_code"] == "91420100MA4K00001"


class TestTechProfileItem:
    """技术画像 Item 验证"""

    def test_required_fields(self):
        item = TechProfileItem()
        required = [
            "company_id", "company_name", "tech_stack", "github_org",
            "github_stars", "tech_blog_url", "cloud_provider",
            "has_github_org", "has_tech_blog", "ai_job_ratio",
        ]
        for field in required:
            assert field in item.fields, f"TechProfileItem 缺少字段: {field}"

    def test_can_set_values(self):
        item = TechProfileItem()
        item["ai_job_ratio"] = 0.35
        item["cloud_provider"] = "AWS"
        assert item["ai_job_ratio"] == 0.35


class TestRecruitmentItem:
    """招聘信息 Item 验证"""

    def test_required_fields(self):
        item = RecruitmentItem()
        required = [
            "company_id", "company_name", "position_title",
            "salary_range", "salary_min", "salary_max",
            "tech_keywords", "headcount", "source_url", "source_name",
        ]
        for field in required:
            assert field in item.fields, f"RecruitmentItem 缺少字段: {field}"


class TestNewsMentionItem:
    """新闻舆情 Item 验证"""

    def test_required_fields(self):
        item = NewsMentionItem()
        required = [
            "company_id", "company_name", "title", "content_summary",
            "source_url", "source_name", "published_at",
            "sentiment_score", "relevance_score", "is_digital_related",
        ]
        for field in required:
            assert field in item.fields, f"NewsMentionItem 缺少字段: {field}"


class TestBiddingItem:
    """招投标 Item 验证"""

    def test_required_fields(self):
        item = BiddingItem()
        required = [
            "company_id", "company_name", "project_name",
            "project_type", "budget_amount", "is_digital",
            "bid_date", "source_url", "source_name",
        ]
        for field in required:
            assert field in item.fields, f"BiddingItem 缺少字段: {field}"


class TestCrawlTaskItem:
    """爬虫任务追踪 Item 验证"""

    def test_required_fields(self):
        item = CrawlTaskItem()
        required = [
            "task_type", "source_name", "target_url",
            "priority", "status", "result_summary",
        ]
        for field in required:
            assert field in item.fields, f"CrawlTaskItem 缺少字段: {field}"
