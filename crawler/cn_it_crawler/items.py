"""Scrapy Item 定义 — 与数据库表一一对应"""

import scrapy


class CompanyItem(scrapy.Item):
    """企业主表 -> companies"""
    company_name = scrapy.Field()
    credit_code = scrapy.Field()
    registered_capital = scrapy.Field()
    capital_amount = scrapy.Field()
    established_date = scrapy.Field()
    legal_representative = scrapy.Field()
    business_scope = scrapy.Field()
    registered_address = scrapy.Field()
    status = scrapy.Field()
    industry_tags = scrapy.Field()
    source_url = scrapy.Field()


class TechProfileItem(scrapy.Item):
    """技术画像 -> tech_profiles"""
    company_id = scrapy.Field()
    company_name = scrapy.Field()
    tech_stack = scrapy.Field()
    github_org = scrapy.Field()
    github_stars = scrapy.Field()
    tech_blog_url = scrapy.Field()
    cloud_provider = scrapy.Field()
    has_github_org = scrapy.Field()
    has_tech_blog = scrapy.Field()
    ai_job_ratio = scrapy.Field()


class RecruitmentItem(scrapy.Item):
    """招聘信息 -> recruitments"""
    company_id = scrapy.Field()
    company_name = scrapy.Field()
    position_title = scrapy.Field()
    salary_range = scrapy.Field()
    salary_min = scrapy.Field()
    salary_max = scrapy.Field()
    tech_keywords = scrapy.Field()
    headcount = scrapy.Field()
    source_url = scrapy.Field()
    source_name = scrapy.Field()


class NewsMentionItem(scrapy.Item):
    """新闻舆情 -> news_mentions"""
    company_id = scrapy.Field()
    company_name = scrapy.Field()
    title = scrapy.Field()
    content_summary = scrapy.Field()
    source_url = scrapy.Field()
    source_name = scrapy.Field()
    published_at = scrapy.Field()
    sentiment_score = scrapy.Field()
    relevance_score = scrapy.Field()
    is_digital_related = scrapy.Field()


class BiddingItem(scrapy.Item):
    """招投标 -> bidding_records"""
    company_id = scrapy.Field()
    company_name = scrapy.Field()
    project_name = scrapy.Field()
    project_type = scrapy.Field()
    budget_amount = scrapy.Field()
    is_digital = scrapy.Field()
    bid_date = scrapy.Field()
    source_url = scrapy.Field()
    source_name = scrapy.Field()


class CrawlTaskItem(scrapy.Item):
    """爬虫任务追踪 -> crawl_tasks"""
    task_type = scrapy.Field()
    source_name = scrapy.Field()
    target_url = scrapy.Field()
    priority = scrapy.Field()
    status = scrapy.Field()
    result_summary = scrapy.Field()
