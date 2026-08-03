"""① 去重管道 — 支持所有 Item 类型去重"""

import logging
import psycopg2
from scrapy.exceptions import DropItem

from wuhan_it_crawler.items import (
    CompanyItem, TechProfileItem, RecruitmentItem,
    NewsMentionItem, BiddingItem,
)

logger = logging.getLogger(__name__)


class DedupPipeline:
    """基于类型感知的去重，防止重复入库"""

    def __init__(self, database_url):
        self.database_url = database_url
        self.conn = None
        # CompanyItem 去重
        self.seen_credit_codes = set()
        # TechProfileItem 去重
        self.seen_tech_company_ids = set()
        # RecruitmentItem 去重
        self.seen_recruitments = set()  # (company_id, position_title, source_name)
        # NewsMentionItem 去重
        self.seen_news = set()  # (company_id, title, source_name)
        # BiddingItem 去重
        self.seen_bidding = set()  # (company_id, project_name, source_name)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(database_url=crawler.settings.get('DATABASE_URL'))

        # TechProfileItem 会话内去重
        self._session_tech_company_ids = set()

    def open_spider(self, spider):
        self.conn = psycopg2.connect(self.database_url)
        with self.conn.cursor() as cur:
            # 加载已有 credit_codes
            cur.execute("SELECT credit_code FROM companies WHERE credit_code IS NOT NULL")
            self.seen_credit_codes = {row[0] for row in cur.fetchall()}

            # 加载已有 tech_profiles
            cur.execute("SELECT company_id FROM tech_profiles")
            self.seen_tech_company_ids = {row[0] for row in cur.fetchall()}

            # 加载已有 recruitments
            cur.execute("SELECT company_id, position_title, source_name FROM recruitments")
            self.seen_recruitments = {(row[0], row[1], row[2]) for row in cur.fetchall()}

            # 加载已有 news_mentions
            cur.execute("SELECT company_id, title, source_name FROM news_mentions")
            self.seen_news = {(row[0], row[1], row[2]) for row in cur.fetchall()}

            # 加载已有 bidding_records
            cur.execute("SELECT company_id, project_name, source_name FROM bidding_records")
            self.seen_bidding = {(row[0], row[1], row[2]) for row in cur.fetchall()}

    def close_spider(self, spider):
        if self.conn:
            self.conn.close()

    def process_item(self, item, spider):
        if isinstance(item, CompanyItem):
            return self._dedup_company(item)
        elif isinstance(item, TechProfileItem):
            return self._dedup_tech_profile(item)
        elif isinstance(item, RecruitmentItem):
            return self._dedup_recruitment(item)
        elif isinstance(item, NewsMentionItem):
            return self._dedup_news_mention(item)
        elif isinstance(item, BiddingItem):
            return self._dedup_bidding(item)
        return item

    def _dedup_company(self, item):
        credit_code = item.get('credit_code')
        if credit_code and credit_code in self.seen_credit_codes:
            logger.debug(f"跳过重复企业: {item.get('company_name')} ({credit_code})")
            raise DropItem(f"重复企业: {credit_code}")
        if credit_code:
            self.seen_credit_codes.add(credit_code)
        return item

    def _dedup_tech_profile(self, item):
        """TechProfileItem: 不做去重，StandardizePipeline 用 ON CONFLICT DO UPDATE 处理"""
        return item

    def _dedup_recruitment(self, item):
        key = (
            item.get('company_id'),
            item.get('position_title', ''),
            item.get('source_name', ''),
        )
        if key in self.seen_recruitments:
            logger.debug(f"跳过重复招聘: {key}")
            raise DropItem(f"重复招聘: {key}")
        self.seen_recruitments.add(key)
        return item

    def _dedup_news_mention(self, item):
        key = (
            item.get('company_id'),
            (item.get('title', '') or '')[:200],  # 截断避免超长标题
            item.get('source_name', ''),
        )
        if key in self.seen_news:
            logger.debug(f"跳过重复新闻: {key}")
            raise DropItem(f"重复新闻: {key}")
        self.seen_news.add(key)
        return item

    def _dedup_bidding(self, item):
        key = (
            item.get('company_id'),
            item.get('project_name', ''),
            item.get('source_name', ''),
        )
        if key in self.seen_bidding:
            logger.debug(f"跳过重复招投标: {key}")
            raise DropItem(f"重复招投标: {key}")
        self.seen_bidding.add(key)
        return item
