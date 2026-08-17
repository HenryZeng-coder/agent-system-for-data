"""新闻舆情爬虫 — 百度新闻 / 搜狗新闻

采集字段: company_name, title, content_summary, source_url, source_name,
          published_at, sentiment_score, relevance_score, is_digital_related

策略:
1. 从数据库 companies 表读取已入库企业列表
2. 搜索 "武汉 + {企业名}" 获取新闻
3. 百度新闻为主，搜狗新闻为备
4. 简单情感分析: 正面词 +0.5, 负面词 -0.5
5. 数字化相关度判断
6. yield NewsMentionItem
"""

import re
import logging
import psycopg2
from urllib.parse import quote_plus
from datetime import datetime

import scrapy
from scrapy.utils.project import get_project_settings

from wuhan_it_crawler.items import NewsMentionItem

logger = logging.getLogger(__name__)


class NewsSpider(scrapy.Spider):
    """武汉IT企业新闻舆情采集 Spider"""

    name = 'news'
    allowed_domains = ['baidu.com', 'sogou.com']

    # ---- 搜索源配置 ----
    BAIDU_NEWS_URL = 'https://news.baidu.com/ns'
    SOGOU_NEWS_URL = 'https://news.sogou.com/news'
    BING_NEWS_URL = 'https://www.bing.com/news/search'   # 必应新闻
    S360_NEWS_URL = 'https://news.so.com/ns'             # 360新闻

    # ---- 情感分析词库 ----
    POSITIVE_WORDS = ['获融', '融资', '发布', '创新', '突破', '领先', '增长', '签约', '合作', '上市', '获奖', '认可', '完成', '提升']
    NEGATIVE_WORDS = ['亏损', '处罚', '违规', '裁员', '破产', '诉讼', '违约', '下降', '关闭', '停业', '失信', '警示']

    # ---- 数字化相关关键词 ----
    DIGITAL_KEYWORDS = ['数字化转型', 'AI', '人工智能', '云计算', '大模型', '数字化', '智能化', '智慧', '数据驱动', '上云']

    # ---- 自定义设置 ----
    custom_settings = {
        'CONCURRENT_REQUESTS_PER_DOMAIN': 2,
        'DOWNLOAD_DELAY': 1.0,
        'DOWNLOAD_TIMEOUT': 30,
        'RETRY_TIMES': 3,
    }

    def __init__(self, mode='incremental', company=None, *args, **kwargs):
        """
        Args:
            mode: 'incremental' (仅搜索新企业) 或 'full' (全量重搜)
            company: 可选，指定单个企业名称 (调试用)
        """
        super().__init__(*args, **kwargs)
        self.mode = mode
        self.company_override = company
        self.companies = []
        self.stats = {
            'search_requests': 0,
            'items_yielded': 0,
            'items_dropped': 0,
        }

        # 在 __init__ 中加载企业
        self._load_companies()

    async def start(self):
        """根据企业列表生成搜索请求，直接分发到对应解析器"""
        if not self.companies:
            self.logger.warning("未找到任何企业，跳过新闻采集")
            return

        self.logger.info(f"启动新闻舆情爬虫, 模式={self.mode}, 企业数={len(self.companies)}")

        for company in self.companies:
            name = company['company_name']
            keyword = f'武汉 {name}'
            meta = {'company_id': company['id'], 'company_name': name}

            # 百度新闻搜索
            self.stats['search_requests'] += 1
            yield scrapy.Request(
                url=f'{self.BAIDU_NEWS_URL}?word={quote_plus(keyword)}&tn=news&from=news&cl=2&rn=20',
                callback=self.parse_baidu,
                meta=meta,
                errback=self.errback_request,
            )

            # 搜狗新闻搜索
            self.stats['search_requests'] += 1
            yield scrapy.Request(
                url=f'{self.SOGOU_NEWS_URL}?query={quote_plus(keyword)}&sort=1',
                callback=self.parse_sogou,
                meta=meta,
                errback=self.errback_request,
            )

            # 必应新闻搜索
            self.stats['search_requests'] += 1
            yield scrapy.Request(
                url=f'{self.BING_NEWS_URL}?q={quote_plus(keyword)}&qft=interval%3d%228%22',
                callback=self.parse_bing_news,
                meta=meta,
                errback=self.errback_request,
            )

            # 360新闻搜索
            self.stats['search_requests'] += 1
            yield scrapy.Request(
                url=f'{self.S360_NEWS_URL}?q={quote_plus(keyword)}',
                callback=self.parse_s360_news,
                meta=meta,
                errback=self.errback_request,
            )

    def closed(self, reason):
        """Spider 关闭时输出统计"""
        self.logger.info(
            f"新闻爬虫结束: 搜索请求={self.stats['search_requests']}, "
            f"产出={self.stats['items_yielded']}, "
            f"丢弃={self.stats['items_dropped']}"
        )

    # ================================================================
    # 百度新闻解析
    # ================================================================

    def parse_baidu(self, response):
        """解析百度新闻搜索结果"""
        company_id = response.meta['company_id']
        company_name = response.meta['company_name']

        # 百度新闻结果条目 — 宽泛回退选择器
        # 百度可能返回反爬非文本响应 (NotSupported)，降级为无结果
        try:
            articles = list(response.css('div.result, div.news-item, div[class*="result"]'))
        except Exception:
            self.logger.warning(f"百度新闻响应解析失败(可能被反爬): {company_name}")
            return

        for article in articles:
            try:
                title_el = article.css('h3 a, .c-title a, a.news-title-font_1xS-F')
                # 使用 getall() + join 处理子元素文本
                title = ''.join(title_el.css('::text').getall()).strip()

                source_url = title_el.attrib.get('href', '')

                # 摘要 — 多级回退
                summary = article.css('.c-summary, .c-span-last p, .c-abstract::text').get('')
                if not summary:
                    summary_parts = article.css('.c-summary::text, .c-abstract::text').getall()
                    summary = ''.join(summary_parts).strip()
                if not summary:
                    summary_parts = article.css('p::text, span::text').getall()
                    summary = ''.join(s.strip() for s in summary_parts if s.strip())

                # 来源和时间
                source_info = article.css('.c-color-gray, .c-gap-right-xsmall::text, .news-source::text').getall()
                source_text = ' '.join(s.strip() for s in source_info if s.strip())

                published_at = self._extract_date(source_text)

                if not title:
                    continue

                item = self._build_item(
                    company_id=company_id,
                    company_name=company_name,
                    title=title,
                    summary=summary,
                    source_url=source_url,
                    source_name='baidu',
                    published_at=published_at,
                )
                if item:
                    self.stats['items_yielded'] += 1
                    yield item

            except Exception as e:
                self.logger.debug(f"百度新闻条目解析失败: {e}")
                self.stats['items_dropped'] += 1

    # ================================================================
    # 搜狗新闻解析
    # ================================================================

    def parse_sogou(self, response):
        """解析搜狗新闻搜索结果"""
        company_id = response.meta['company_id']
        company_name = response.meta['company_name']

        # 搜狗新闻结果条目 — 宽泛回退选择器
        # 搜狗可能返回反爬非文本响应 (NotSupported)，降级为无结果
        try:
            articles = list(response.css('div.news-list li, div[class*="vrwrap"], div[class*="result"]'))
        except Exception:
            self.logger.warning(f"搜狗新闻响应解析失败(可能被反爬): {company_name}")
            return

        for article in articles:
            try:
                title_el = article.css('h3 a, a.news-title, a[href]')
                # 使用 getall() + join 处理子元素文本
                title = ''.join(title_el.css('::text').getall()).strip()

                source_url = title_el.attrib.get('href', '')
                if source_url and not source_url.startswith('http'):
                    source_url = f'https://news.sogou.com{source_url}'

                # 摘要
                summary = article.css('.news-detail, .star-wiki, p.txt-info::text').get('')
                if not summary:
                    summary_parts = article.css('.news-detail::text, p::text').getall()
                    summary = ''.join(s.strip() for s in summary_parts if s.strip())

                # 时间
                time_text = article.css('.news-from span, .time::text, .c-gray::text').get('')
                published_at = self._extract_date(time_text or '')

                if not title:
                    continue

                item = self._build_item(
                    company_id=company_id,
                    company_name=company_name,
                    title=title,
                    summary=summary,
                    source_url=source_url,
                    source_name='sogou',
                    published_at=published_at,
                )
                if item:
                    self.stats['items_yielded'] += 1
                    yield item

            except Exception as e:
                self.logger.debug(f"搜狗新闻条目解析失败: {e}")
                self.stats['items_dropped'] += 1

    # ================================================================
    # 必应新闻解析
    # ================================================================

    def parse_bing_news(self, response):
        """解析必应新闻搜索结果"""
        company_id = response.meta['company_id']
        company_name = response.meta['company_name']

        # 必应新闻结果条目 — 宽泛回退选择器
        try:
            articles = list(response.css('div.news-card, div.newsitem, div[class*="news"]'))
        except Exception:
            self.logger.warning(f"必应新闻响应解析失败(可能被反爬): {company_name}")
            return

        for article in articles:
            try:
                title_el = article.css('a.title, h2 a, a[class*="title"]')
                title = ''.join(title_el.css('::text').getall()).strip()

                source_url = title_el.attrib.get('href', '')
                if source_url and not source_url.startswith('http'):
                    source_url = f'https://www.bing.com{source_url}'

                # 摘要
                summary = article.css('.snippet, .news-summary, p::text').get('')
                if not summary:
                    summary_parts = article.css('.snippet::text, p::text').getall()
                    summary = ''.join(s.strip() for s in summary_parts if s.strip())

                # 来源和时间
                source_text = ' '.join(
                    s.strip() for s in article.css('.source, .news-source, span::text').getall()
                    if s.strip()
                )
                published_at = self._extract_date(source_text)

                if not title:
                    continue

                item = self._build_item(
                    company_id=company_id,
                    company_name=company_name,
                    title=title,
                    summary=summary,
                    source_url=source_url,
                    source_name='bing_news',
                    published_at=published_at,
                )
                if item:
                    self.stats['items_yielded'] += 1
                    yield item

            except Exception as e:
                self.logger.debug(f"必应新闻条目解析失败: {e}")
                self.stats['items_dropped'] += 1

    # ================================================================
    # 360新闻解析
    # ================================================================

    def parse_s360_news(self, response):
        """解析360新闻搜索结果"""
        company_id = response.meta['company_id']
        company_name = response.meta['company_name']

        # 360新闻结果条目
        try:
            articles = list(response.css('div.news-item, li[class*="news"], div[class*="result"]'))
        except Exception:
            self.logger.warning(f"360新闻响应解析失败(可能被反爬): {company_name}")
            return

        for article in articles:
            try:
                title_el = article.css('h3 a, a[class*="title"], a[href]')
                title = ''.join(title_el.css('::text').getall()).strip()

                source_url = title_el.attrib.get('href', '')
                if source_url and not source_url.startswith('http'):
                    source_url = f'https://news.so.com{source_url}'

                # 摘要
                summary = article.css('.news-desc, .summary, p::text').get('')
                if not summary:
                    summary_parts = article.css('.news-desc::text, p::text').getall()
                    summary = ''.join(s.strip() for s in summary_parts if s.strip())

                # 时间
                time_text = article.css('.news-time, .time, .src-time::text').get('')
                published_at = self._extract_date(time_text or '')

                if not title:
                    continue

                item = self._build_item(
                    company_id=company_id,
                    company_name=company_name,
                    title=title,
                    summary=summary,
                    source_url=source_url,
                    source_name='so360_news',
                    published_at=published_at,
                )
                if item:
                    self.stats['items_yielded'] += 1
                    yield item

            except Exception as e:
                self.logger.debug(f"360新闻条目解析失败: {e}")
                self.stats['items_dropped'] += 1

    # ================================================================
    # Item 构建
    # ================================================================

    def _build_item(self, company_id, company_name, title, summary,
                    source_url, source_name, published_at) -> NewsMentionItem:
        """从原始数据构建 NewsMentionItem"""
        title = title.strip()
        if not title:
            return None

        # 组合标题和摘要用于分析
        full_text = f'{title} {summary}'

        # 情感分析
        sentiment_score = self._analyze_sentiment(full_text)

        # 数字化相关度
        is_digital = self._check_digital_related(full_text)
        relevance_score = self._calc_relevance(company_name, full_text, is_digital)

        item = NewsMentionItem()
        item['company_id'] = company_id
        item['company_name'] = company_name
        item['title'] = title
        item['content_summary'] = summary.strip() or None
        item['source_url'] = source_url or None
        item['source_name'] = source_name
        item['published_at'] = published_at
        item['sentiment_score'] = sentiment_score
        item['relevance_score'] = relevance_score
        item['is_digital_related'] = is_digital

        return item

    # ================================================================
    # 情感分析 (简单关键词匹配)
    # ================================================================

    def _analyze_sentiment(self, text: str) -> float:
        """
        简单情感分析:
        - 正面词 +0.5
        - 负面词 -0.5
        - 范围 [-1.0, 1.0]
        """
        score = 0.0
        for word in self.POSITIVE_WORDS:
            if word in text:
                score += 0.5
        for word in self.NEGATIVE_WORDS:
            if word in text:
                score -= 0.5

        return max(-1.0, min(1.0, score))

    # ================================================================
    # 数字化相关度判断
    # ================================================================

    def _check_digital_related(self, text: str) -> bool:
        """判断新闻是否与数字化转型相关"""
        return any(kw in text for kw in self.DIGITAL_KEYWORDS)

    def _calc_relevance(self, company_name: str, text: str, is_digital: bool) -> float:
        """
        计算新闻与企业相关度 (0-1.0):
        - 企业名直接出现: +0.5
        - 数字化相关: +0.3
        - 正面情感: +0.2
        """
        score = 0.0
        if company_name and company_name in text:
            score += 0.5
        if is_digital:
            score += 0.3
        sentiment = self._analyze_sentiment(text)
        if sentiment > 0:
            score += 0.2
        return min(1.0, score)

    # ================================================================
    # 工具方法
    # ================================================================

    def _extract_date(self, text: str) -> str:
        """从来源文本中提取日期"""
        if not text:
            return None

        # 匹配 YYYY-MM-DD 或 YYYY年MM月DD日
        patterns = [
            r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})',
            r'(\d{4}年\d{1,2}月\d{1,2}日)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                date_str = match.group(1)
                # 统一为 YYYY-MM-DD
                date_str = date_str.replace('年', '-').replace('月', '-').replace('日', '')
                date_str = date_str.replace('/', '-')
                return date_str

        # 匹配 X小时前 / X天前
        hours_match = re.search(r'(\d+)\s*小时前', text)
        if hours_match:
            return datetime.now().strftime('%Y-%m-%d')

        days_match = re.search(r'(\d+)\s*天前', text)
        if days_match:
            from datetime import timedelta
            days = int(days_match.group(1))
            return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # "刚刚" / "今天"
        if '刚刚' in text or '今天' in text:
            return datetime.now().strftime('%Y-%m-%d')

        return None

    def _load_companies(self):
        """从数据库读取企业列表"""
        settings = get_project_settings()
        database_url = settings.get('DATABASE_URL')

        if not database_url:
            self.logger.warning("DATABASE_URL 未配置")
            return

        try:
            conn = psycopg2.connect(database_url)
            with conn.cursor() as cur:
                if self.company_override:
                    cur.execute(
                        "SELECT id, company_name FROM companies WHERE company_name = %s",
                        (self.company_override,)
                    )
                else:
                    cur.execute("SELECT id, company_name FROM companies ORDER BY id")

                self.companies = [
                    {'id': row[0], 'company_name': row[1]}
                    for row in cur.fetchall()
                ]
            conn.close()
            self.logger.info(f"加载企业 {len(self.companies)} 家")
        except Exception as e:
            self.logger.error(f"加载企业列表失败: {e}")

    # ================================================================
    # 错误回调
    # ================================================================

    def errback_request(self, failure):
        """请求错误回调"""
        self.logger.error(f"请求失败: {failure.request.url}, error={failure.value}")
