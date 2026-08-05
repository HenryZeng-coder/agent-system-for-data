"""招投标爬虫 — 搜索引擎聚合

采集字段: company_id, company_name, project_name, project_type,
          budget_amount, is_digital, bid_date, source_url, source_name

策略:
1. 使用 WebSearchEngine 搜索 "武汉 信息化 招标/采购" 等关键词
2. 从搜索结果中提取招标项目信息
3. 识别数字化项目
4. 匹配中标企业与 companies 表
5. yield BiddingItem

注意: ccgp.gov.cn 反爬严格，改用搜索引擎聚合获取招标信息
"""

import re
import logging
import psycopg2
from urllib.parse import quote_plus
from datetime import datetime, timedelta

import scrapy
from scrapy.utils.project import get_project_settings

from wuhan_it_crawler.items import BiddingItem

logger = logging.getLogger(__name__)


class BiddingSpider(scrapy.Spider):
    """武汉政府采购招投标采集 Spider — 搜索引擎聚合"""

    name = 'bidding'
    allowed_domains = []

    CCGP_SEARCH_URL = 'http://search.ccgp.gov.cn/bxsearch'

    SEARCH_KEYWORDS = [
        '武汉 信息化 招标', '武汉 数字化 采购', '武汉 AI 招标',
        '武汉 人工智能 采购', '武汉 云计算 招标', '武汉 大数据 采购',
        '武汉 智慧城市 招标', '武汉 软件开发 采购',
    ]

    DIGITAL_KEYWORDS = [
        '数字化', '信息化', '智能', 'AI', '人工智能', '云计算',
        '大数据', '智慧城市', '软件', '数据中台', '上云',
        '电子政务', '网络安全', '信息技术', '系统集成',
    ]

    # 公司名后缀 — 用于模糊匹配时剥离
    COMPANY_SUFFIXES = ['股份有限公司', '有限责任公司', '有限公司', '集团']

    custom_settings = {
        'CONCURRENT_REQUESTS': 4,
        'DOWNLOAD_DELAY': 1.0,
        'DOWNLOAD_TIMEOUT': 30,
        'RETRY_TIMES': 3,
    }

    def __init__(self, keyword=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.keyword_override = keyword
        self.companies_map = {}
        self.stats = {
            'search_requests': 0, 'detail_requests': 0,
            'items_yielded': 0, 'digital_count': 0, 'items_dropped': 0,
        }

        self._load_companies()

    async def start(self):
        keywords = [self.keyword_override] if self.keyword_override else self.SEARCH_KEYWORDS
        self.logger.info(f"启动招投标爬虫, 关键词数={len(keywords)}, 已知企业={len(self.companies_map)}")

        try:
            import sys
            sys.path.insert(0, '/Users/henry/Desktop/repository/E-InfoInsigth-agent-codes')
            from engine.websearch import WebSearchEngine
            search_engine = WebSearchEngine()
        except ImportError:
            from engine.websearch import WebSearchEngine
            search_engine = WebSearchEngine()

        for kw in keywords:
            self.stats['search_requests'] += 1
            try:
                results = search_engine.search(kw, limit=10)
                for result in results:
                    title = result.get('title', '')
                    summary = result.get('summary', '')
                    url = result.get('url', '')
                    source = result.get('source', 'unknown')

                    text = f'{title} {summary}'

                    # 从文本中提取项目名
                    project_name = self._extract_project_name(text)
                    if not project_name:
                        continue

                    # 过滤明显不是招标项目的内容
                    if not self._is_bidding_related(text):
                        continue

                    is_digital = self._check_digital(text)
                    budget_amount = self._parse_budget(text)
                    bid_date = self._extract_date(text)
                    company_id, company_name = self._match_company(text)
                    project_type = self._extract_project_type(text)

                    item = BiddingItem()
                    item['company_id'] = company_id
                    item['company_name'] = company_name
                    item['project_name'] = project_name
                    item['project_type'] = project_type
                    item['budget_amount'] = budget_amount
                    item['is_digital'] = is_digital
                    item['bid_date'] = bid_date
                    item['source_url'] = url
                    item['source_name'] = f'websearch_{source}'

                    self.stats['items_yielded'] += 1
                    if is_digital:
                        self.stats['digital_count'] += 1
                    yield item

            except Exception as e:
                self.logger.error(f"搜索招投标失败: {kw}, error={e}")

        self.logger.info(
            f"招投标搜索完成: 产出={self.stats['items_yielded']}, "
            f"数字化={self.stats['digital_count']}"
        )

        # yield dummy request
        yield scrapy.Request(url='data:,', callback=self.parse_dummy, dont_filter=True)

    def parse_dummy(self, response):
        pass

    def closed(self, reason):
        self.logger.info(
            f"招投标爬虫结束: 搜索={self.stats['search_requests']}, "
            f"产出={self.stats['items_yielded']}, "
            f"数字化={self.stats['digital_count']}, "
            f"丢弃={self.stats['items_dropped']}"
        )

    # ================================================================
    # 信息提取
    # ================================================================

    def _extract_project_name(self, text):
        """从文本中提取招标项目名称"""
        # 常见招标项目模式
        patterns = [
            r'([^\s,，。、|/<>"]{5,80}(?:采购|招标|竞争|磋商|询价|谈判)[^\s,，。、|/<>"]{0,40})',
            r'(项目名称[：:]\s*[^\s,，。]{5,80})',
        ]
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                name = m.group(1).strip()
                # 清理
                name = re.sub(r'^[：:】\]]', '', name)
                name = re.sub(r'[【\[]', '', name)
                if 5 < len(name) < 100:
                    return name
        # 如果没匹配到模式，返回标题本身（截断）
        if len(text) > 5:
            # 截取到第一个标点
            m = re.match(r'([^\s,，。！？、]{5,80})', text)
            if m:
                return m.group(1)
        return None

    def _is_bidding_related(self, text):
        """判断文本是否与招标采购相关"""
        bidding_words = ['采购', '招标', '竞争', '磋商', '询价', '谈判',
                         '中标', '成交', '公告', '公示', '预算']
        return any(kw in text for kw in bidding_words)

    def _match_company(self, text):
        """匹配文本中提到的企业 — 精确匹配 + 标准化名模糊匹配"""
        # 1) 精确全名子串匹配（最高优先）
        for name, cid in self.companies_map.items():
            if name in text:
                return cid, name
        # 2) 标准化名子串匹配（去后缀后，最短 4 字符避免误匹配）
        for name, cid in self.companies_map.items():
            short = self._normalize_name(name)
            if len(short) >= 4 and short in text:
                return cid, name
        return None, None

    @classmethod
    def _normalize_name(cls, name):
        """剥离公司名后缀，用于模糊匹配"""
        for suffix in cls.COMPANY_SUFFIXES:
            if name.endswith(suffix):
                return name[:-len(suffix)]
        return name

    def _check_digital(self, text):
        return any(kw in text for kw in self.DIGITAL_KEYWORDS)

    def _parse_budget(self, text):
        if not text:
            return None
        m = re.search(r'(\d+\.?\d*)\s*万', text)
        if m:
            return float(m.group(1))
        m = re.search(r'(\d+\.?\d*)\s*亿', text)
        if m:
            return float(m.group(1)) * 10000
        m = re.search(r'(\d+\.?\d*)\s*元', text)
        if m:
            return float(m.group(1)) / 10000
        return None

    def _extract_project_type(self, text):
        for kw, pt in [('竞争性谈判', '竞争性谈判'), ('单一来源', '单一来源采购'),
                       ('磋商', '竞争性磋商'), ('询价', '询价采购'),
                       ('招标', '公开招标'), ('采购', '政府采购')]:
            if kw in text:
                return pt
        return '其他'

    def _extract_date(self, text):
        if not text:
            return None
        for p in [r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', r'(\d{4}年\d{1,2}月\d{1,2}日)']:
            m = re.search(p, text)
            if m:
                return m.group(1).replace('年', '-').replace('月', '-').replace('日', '').replace('/', '-')
        return None

    def _load_companies(self):
        settings = get_project_settings()
        database_url = settings.get('DATABASE_URL')
        if not database_url:
            return
        try:
            conn = psycopg2.connect(database_url)
            with conn.cursor() as cur:
                cur.execute("SELECT id, company_name FROM companies")
                for row in cur.fetchall():
                    self.companies_map[row[1]] = row[0]
            conn.close()
            self.logger.info(f"加载企业映射 {len(self.companies_map)} 家")
        except Exception as e:
            self.logger.error(f"加载企业列表失败: {e}")

    def errback_request(self, failure):
        self.logger.error(f"请求失败: {failure.request.url}, error={failure.value}")
