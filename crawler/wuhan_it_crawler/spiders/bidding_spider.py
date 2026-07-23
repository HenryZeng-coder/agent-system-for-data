"""招投标爬虫 — 中国政府采购网 (ccgp.gov.cn)

采集字段: company_id, company_name, project_name, project_type,
          budget_amount, is_digital, bid_date, source_url, source_name

策略:
1. 搜索关键词: 武汉 + 信息化/数字化/AI/云计算/大数据
2. 解析项目列表页和详情页
3. 识别数字化项目
4. 匹配中标企业与 companies 表
5. yield BiddingItem
"""

import re
import logging
import psycopg2
from urllib.parse import quote_plus, urljoin
from datetime import datetime, timedelta

import scrapy
from scrapy.utils.project import get_project_settings

from wuhan_it_crawler.items import BiddingItem

logger = logging.getLogger(__name__)


class BiddingSpider(scrapy.Spider):
    """武汉政府采购招投标采集 Spider"""

    name = 'bidding'
    allowed_domains = ['ccgp.gov.cn', 'search.ccgp.gov.cn']

    CCGP_SEARCH_URL = 'http://search.ccgp.gov.cn/bxsearch'

    SEARCH_KEYWORDS = [
        '武汉 信息化', '武汉 数字化', '武汉 AI', '武汉 人工智能',
        '武汉 云计算', '武汉 大数据', '武汉 智慧城市', '武汉 软件开发',
    ]

    DIGITAL_KEYWORDS = [
        '数字化', '信息化', '智能', 'AI', '人工智能', '云计算',
        '大数据', '智慧城市', '软件', '数据中台', '上云',
        '电子政务', '网络安全', '信息技术', '系统集成',
    ]

    custom_settings = {
        'CONCURRENT_REQUESTS_PER_DOMAIN': 1,
        'DOWNLOAD_DELAY': 2.0,
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

    def start_requests(self):
        self._load_companies()
        keywords = [self.keyword_override] if self.keyword_override else self.SEARCH_KEYWORDS
        self.logger.info(f"启动招投标爬虫, 关键词数={len(keywords)}, 已知企业={len(self.companies_map)}")

        for kw in keywords:
            self.stats['search_requests'] += 1
            yield scrapy.Request(
                url=f'{self.CCGP_SEARCH_URL}?searchtype=1&bidSort=0&bidType=1&dbselect=bidx&kw={quote_plus(kw)}&start_time={self._date_range_start()}&end_time={datetime.now().strftime("%Y:%m:%d")}&timeType=6&pppStatus=0&agentName=',
                callback=self.parse_list,
                meta={'search_keyword': kw, 'page': 0},
                errback=self.errback_request,
            )

    def closed(self, reason):
        self.logger.info(
            f"招投标爬虫结束: 搜索={self.stats['search_requests']}, "
            f"详情={self.stats['detail_requests']}, 产出={self.stats['items_yielded']}, "
            f"数字化={self.stats['digital_count']}, 丢弃={self.stats['items_dropped']}"
        )

    def parse_list(self, response):
        kw = response.meta['search_keyword']
        articles = response.css('ul.vT-s-result-list li, div.vT-s-result-list div.vT-z, div.list-box li')
        if not articles:
            articles = response.css('div.vT-s-result-list div, ul.vT-z li')

        for article in articles:
            try:
                title_el = article.css('a[href], p.vT-s-result-title a')
                title = (title_el.css('::text').get('') or '').strip()
                detail_url = title_el.attrib.get('href', '')
                if detail_url and not detail_url.startswith('http'):
                    detail_url = urljoin(response.url, detail_url)
                if not title:
                    continue

                is_digital = self._check_digital(title)
                budget_text = article.css('.vT-s-result-price, .price, span[class*="money"]::text').get('')
                budget_amount = self._parse_budget(budget_text or '')
                date_text = article.css('.vT-s-result-time, .time, span[class*="date"]::text').get('')
                bid_date = self._extract_date(date_text or '')

                if detail_url:
                    self.stats['detail_requests'] += 1
                    yield scrapy.Request(
                        url=detail_url, callback=self.parse_detail,
                        meta={'search_keyword': kw, 'project_name': title,
                              'is_digital': is_digital, 'budget_amount': budget_amount, 'bid_date': bid_date},
                        errback=self.errback_request,
                    )
                else:
                    item = self._build_item(title, self._extract_project_type(title),
                                            budget_amount, is_digital, bid_date, response.url)
                    if item:
                        self.stats['items_yielded'] += 1
                        if item.get('is_digital'): self.stats['digital_count'] += 1
                        yield item
            except Exception as e:
                self.logger.debug(f"列表条目解析失败: {e}")
                self.stats['items_dropped'] += 1

        current_page = response.meta.get('page', 0)
        if current_page < 4 and articles:
            next_page = current_page + 1
            yield scrapy.Request(
                url=f'{self.CCGP_SEARCH_URL}?searchtype=1&bidSort=0&bidType=1&dbselect=bidx&kw={quote_plus(kw)}&start_time={self._date_range_start()}&end_time={datetime.now().strftime("%Y:%m:%d")}&timeType=6&pppStatus=0&agentName=&pageNo={next_page}',
                callback=self.parse_list,
                meta={'search_keyword': kw, 'page': next_page},
                errback=self.errback_request,
            )

    def parse_detail(self, response):
        project_name = response.meta['project_name']
        is_digital = response.meta['is_digital']
        budget_amount = response.meta.get('budget_amount')
        bid_date = response.meta.get('bid_date')

        content = response.css('div.vF-deail-main, div.detail-content, div.vF-detail-content')
        content_text = ' '.join(content.css('::text').getall())

        if not budget_amount:
            budget_el = response.css('.vF-deail-budget, .budget, [class*="money"]::text').getall()
            budget_amount = self._parse_budget(' '.join(budget_el))

        if not bid_date:
            date_el = response.css('.vF-deail-time, .time, [class*="date"]::text').getall()
            bid_date = self._extract_date(' '.join(date_el))

        if not is_digital:
            is_digital = self._check_digital(f'{project_name} {content_text}')

        item = self._build_item(project_name, self._extract_project_type(project_name),
                                budget_amount, is_digital, bid_date, response.url)
        if item:
            self.stats['items_yielded'] += 1
            if item.get('is_digital'): self.stats['digital_count'] += 1
            yield item

    def _build_item(self, project_name, project_type, budget_amount, is_digital, bid_date, source_url):
        project_name = project_name.strip()
        if not project_name: return None
        company_id, company_name = self._match_company(project_name)

        item = BiddingItem()
        item['company_id'] = company_id
        item['company_name'] = company_name
        item['project_name'] = project_name
        item['project_type'] = project_type
        item['budget_amount'] = budget_amount
        item['is_digital'] = is_digital
        item['bid_date'] = bid_date
        item['source_url'] = source_url
        item['source_name'] = 'ccgp'
        return item

    def _match_company(self, text):
        for name, cid in self.companies_map.items():
            if name in text: return cid, name
        return None, None

    def _check_digital(self, text):
        return any(kw in text for kw in self.DIGITAL_KEYWORDS)

    def _parse_budget(self, text):
        if not text: return None
        m = re.search(r'(\d+\.?\d*)\s*万', text)
        if m: return float(m.group(1))
        m = re.search(r'(\d+\.?\d*)\s*亿', text)
        if m: return float(m.group(1)) * 10000
        m = re.search(r'(\d+\.?\d*)\s*元', text)
        if m: return float(m.group(1)) / 10000
        return None

    def _extract_project_type(self, title):
        for kw, pt in [('竞争性谈判','竞争性谈判'),('单一来源','单一来源采购'),
                       ('磋商','竞争性磋商'),('询价','询价采购'),
                       ('招标','公开招标'),('采购','政府采购')]:
            if kw in title: return pt
        return '其他'

    def _extract_date(self, text):
        if not text: return None
        for p in [r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', r'(\d{4}年\d{1,2}月\d{1,2}日)']:
            m = re.search(p, text)
            if m: return m.group(1).replace('年','-').replace('月','-').replace('日','').replace('/','-')
        return None

    def _date_range_start(self):
        return (datetime.now() - timedelta(days=180)).strftime('%Y:%m:%d')

    def _load_companies(self):
        settings = get_project_settings()
        database_url = settings.get('DATABASE_URL')
        if not database_url: return
        try:
            conn = psycopg2.connect(database_url)
            with conn.cursor() as cur:
                cur.execute("SELECT id, company_name FROM companies")
                for row in cur.fetchall(): self.companies_map[row[1]] = row[0]
            conn.close()
            self.logger.info(f"加载企业映射 {len(self.companies_map)} 家")
        except Exception as e:
            self.logger.error(f"加载企业列表失败: {e}")

    def errback_request(self, failure):
        self.logger.error(f"请求失败: {failure.request.url}, error={failure.value}")
