"""① 去重管道 — 基于 credit_code"""

import logging
import psycopg2
from scrapy.exceptions import DropItem

logger = logging.getLogger(__name__)


class DedupPipeline:
    """基于 credit_code 去重，防止重复入库"""

    def __init__(self, database_url):
        self.database_url = database_url
        self.conn = None
        self.seen_codes = set()

    @classmethod
    def from_crawler(cls, crawler):
        return cls(database_url=crawler.settings.get('DATABASE_URL'))

    def open_spider(self, spider):
        self.conn = psycopg2.connect(self.database_url)
        # 加载已有 credit_code
        with self.conn.cursor() as cur:
            cur.execute("SELECT credit_code FROM companies WHERE credit_code IS NOT NULL")
            self.seen_codes = {row[0] for row in cur.fetchall()}

    def close_spider(self, spider):
        if self.conn:
            self.conn.close()

    def process_item(self, item, spider):
        credit_code = item.get('credit_code')
        if credit_code and credit_code in self.seen_codes:
            logger.debug(f"跳过重复企业: {item.get('company_name')} ({credit_code})")
            raise DropItem(f"重复企业: {credit_code}")
        if credit_code:
            self.seen_codes.add(credit_code)
        return item
