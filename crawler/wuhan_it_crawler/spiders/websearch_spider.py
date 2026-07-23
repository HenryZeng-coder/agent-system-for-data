"""WebSearch 聚合爬虫 — 百度/搜狗/必应三引擎聚合搜索

采集字段: NewsMentionItem (company_id, company_name, title, content_summary,
          source_url, source_name, published_at, sentiment_score, relevance_score, is_digital_related)

策略: 从数据库读取企业列表, 调用 WebSearchEngine.search() 三引擎并行搜索, yield NewsMentionItem
"""

import logging
import psycopg2
from datetime import datetime

import scrapy
from scrapy.utils.project import get_project_settings

from wuhan_it_crawler.items import NewsMentionItem

logger = logging.getLogger(__name__)


class WebSearchSpider(scrapy.Spider):
    """多引擎聚合搜索 Spider"""

    name = 'websearch'
    allowed_domains = []

    DIGITAL_KEYWORDS = ['数字化转型', 'AI', '人工智能', '云计算', '大模型', '数字化', '智能化']
    POSITIVE_WORDS = ['获融', '融资', '发布', '创新', '突破', '领先', '增长', '签约', '合作']
    NEGATIVE_WORDS = ['亏损', '处罚', '违规', '裁员', '破产']

    custom_settings = {
        'CONCURRENT_REQUESTS': 4,
        'DOWNLOAD_DELAY': 0.5,
        'DOWNLOAD_TIMEOUT': 30,
    }

    def __init__(self, company=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.company_override = company
        self.companies = []
        self.stats = {'items_yielded': 0, 'items_dropped': 0}

    def start_requests(self):
        self._load_companies()
        if not self.companies:
            self.logger.warning("未找到企业，跳过")
            return

        self.logger.info(f"启动WebSearch爬虫, 企业数={len(self.companies)}")

        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        try:
            from engine.websearch import WebSearchEngine
        except ImportError:
            self.logger.error("无法导入 WebSearchEngine")
            return

        engine = WebSearchEngine()

        for company in self.companies:
            name = company['company_name']
            query = f'武汉 {name}'
            try:
                results = engine.search(query, limit=10)
                self.logger.info(f"搜索 '{query}' 返回 {len(results)} 条")
                for r in results:
                    item = self._build_item(
                        company_id=company['id'],
                        company_name=name,
                        title=r.get('title', ''),
                        summary=r.get('summary', ''),
                        source_url=r.get('url', ''),
                        source_name=f"websearch_{r.get('source', 'unknown')}",
                    )
                    if item:
                        self.stats['items_yielded'] += 1
                        yield item
            except Exception as e:
                self.logger.error(f"搜索 '{query}' 失败: {e}")

    def closed(self, reason):
        self.logger.info(
            f"WebSearch爬虫结束: 产出={self.stats['items_yielded']}, "
            f"丢弃={self.stats['items_dropped']}"
        )

    def _build_item(self, company_id, company_name, title, summary,
                    source_url, source_name):
        title = title.strip()
        if not title:
            return None
        full_text = f'{title} {summary}'
        sentiment = self._analyze_sentiment(full_text)
        is_digital = any(kw in full_text for kw in self.DIGITAL_KEYWORDS)
        relevance = min(1.0, (0.5 if company_name and company_name in full_text else 0.0)
                        + (0.3 if is_digital else 0.0)
                        + (0.2 if sentiment > 0 else 0.0))

        item = NewsMentionItem()
        item['company_id'] = company_id
        item['company_name'] = company_name
        item['title'] = title
        item['content_summary'] = summary.strip() or None
        item['source_url'] = source_url or None
        item['source_name'] = source_name
        item['published_at'] = datetime.now().strftime('%Y-%m-%d')
        item['sentiment_score'] = sentiment
        item['relevance_score'] = relevance
        item['is_digital_related'] = is_digital
        return item

    def _analyze_sentiment(self, text):
        score = 0.0
        for w in self.POSITIVE_WORDS:
            if w in text:
                score += 0.5
        for w in self.NEGATIVE_WORDS:
            if w in text:
                score -= 0.5
        return max(-1.0, min(1.0, score))

    def _load_companies(self):
        settings = get_project_settings()
        database_url = settings.get('DATABASE_URL')
        if not database_url:
            return
        try:
            conn = psycopg2.connect(database_url)
            with conn.cursor() as cur:
                if self.company_override:
                    cur.execute(
                        "SELECT id, company_name FROM companies WHERE company_name = %s",
                        (self.company_override,),
                    )
                else:
                    cur.execute("SELECT id, company_name FROM companies ORDER BY id")
                self.companies = [
                    {'id': r[0], 'company_name': r[1]}
                    for r in cur.fetchall()
                ]
            conn.close()
            self.logger.info(f"加载企业 {len(self.companies)} 家")
        except Exception as e:
            self.logger.error(f"加载企业失败: {e}")
