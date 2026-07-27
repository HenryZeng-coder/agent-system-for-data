"""Spider 名称与注册验证 — 确保6个Spider名称正确且可被Scrapy识别"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "crawler"))

from wuhan_it_crawler.spiders.business_spider import BusinessSpider
from wuhan_it_crawler.spiders.tech_spider import TechSpider
from wuhan_it_crawler.spiders.recruitment_spider import RecruitmentSpider
from wuhan_it_crawler.spiders.news_spider import NewsSpider
from wuhan_it_crawler.spiders.bidding_spider import BiddingSpider
from wuhan_it_crawler.spiders.websearch_spider import WebSearchSpider


class TestSpiderNames:
    """验证6个Spider的name属性"""

    def test_business_spider_name(self):
        assert BusinessSpider.name == "business"

    def test_tech_spider_name(self):
        assert TechSpider.name == "tech"

    def test_recruitment_spider_name(self):
        assert RecruitmentSpider.name == "recruitment"

    def test_news_spider_name(self):
        assert NewsSpider.name == "news"

    def test_bidding_spider_name(self):
        assert BiddingSpider.name == "bidding"

    def test_websearch_spider_name(self):
        assert WebSearchSpider.name == "websearch"


class TestSpiderNamesUnique:
    """验证6个Spider名称互不重复"""

    def test_all_names_unique(self):
        names = [
            BusinessSpider.name,
            TechSpider.name,
            RecruitmentSpider.name,
            NewsSpider.name,
            BiddingSpider.name,
            WebSearchSpider.name,
        ]
        assert len(names) == len(set(names)), f"Spider名称有重复: {names}"


class TestSpiderInheritance:
    """验证所有Spider继承自 scrapy.Spider"""

    def test_business_inherits_spider(self):
        import scrapy
        assert issubclass(BusinessSpider, scrapy.Spider)

    def test_tech_inherits_spider(self):
        import scrapy
        assert issubclass(TechSpider, scrapy.Spider)

    def test_recruitment_inherits_spider(self):
        import scrapy
        assert issubclass(RecruitmentSpider, scrapy.Spider)

    def test_news_inherits_spider(self):
        import scrapy
        assert issubclass(NewsSpider, scrapy.Spider)

    def test_bidding_inherits_spider(self):
        import scrapy
        assert issubclass(BiddingSpider, scrapy.Spider)

    def test_websearch_inherits_spider(self):
        import scrapy
        assert issubclass(WebSearchSpider, scrapy.Spider)
