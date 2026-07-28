"""工商信息爬虫 — 国家企业信用信息公示系统 (gsxt.gov.cn)

双通道采集策略:
- 主通道: gsxt.gov.cn (Playwright 动态渲染)
- 备通道: 天眼查等第三方聚合站

采集字段: company_name, credit_code, registered_capital, established_date,
          legal_representative, business_scope, registered_address, industry_tags
"""

import re
import json
import logging
import psycopg2
from urllib.parse import quote_plus
from datetime import datetime

import scrapy
from scrapy import signals
from scrapy.utils.project import get_project_settings

from wuhan_it_crawler.items import CompanyItem

logger = logging.getLogger(__name__)


class BusinessSpider(scrapy.Spider):
    """武汉IT企业工商信息采集 Spider"""

    name = 'business'
    allowed_domains = ['gsxt.gov.cn', 'tianyancha.com', 'qcc.com']

    # ---- 搜索关键词 ----
    locations = ['武汉']
    industries = ['软件开发', '信息技术', '科技', '人工智能', '云计算', '大数据', '数字化']

    # ---- gsxt.gov.cn 配置 ----
    GSXT_BASE_URL = 'https://www.gsxt.gov.cn'
    GSXT_SEARCH_URL = 'https://www.gsxt.gov.cn/SearchItemCaptcha'

    # ---- 自定义设置 ----
    custom_settings = {
        'CONCURRENT_REQUESTS_PER_DOMAIN': 2,
        'DOWNLOAD_DELAY': 1.0,           # gsxt 反爬严，加大延迟
        'DOWNLOAD_TIMEOUT': 60,
        'PLAYWRIGHT_BROWSER_TYPE': 'chromium',
        'PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT': 30000,
        'TWISTED_REACTOR': 'twisted.internet.asyncioreactor.AsyncioSelectorReactor',
        'DOWNLOAD_HANDLERS': {
            'http': 'scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler',
            'https': 'scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler',
        },
    }

    def __init__(self, mode='incremental', keyword=None, *args, **kwargs):
        """
        Args:
            mode: 'incremental' (仅新企业) 或 'full' (全量重跑)
            keyword: 可选，指定单个搜索关键词 (调试用)
        """
        super().__init__(*args, **kwargs)
        self.mode = mode
        self.keyword_override = keyword
        self.seen_credit_codes = set()
        self.stats = {
            'search_requests': 0,
            'detail_requests': 0,
            'items_yielded': 0,
            'items_dropped_dedup': 0,
            'captcha_encountered': 0,
        }

        # 在 __init__ 中准备搜索关键词和 start_urls
        self._load_existing_codes()
        if self.keyword_override:
            keywords = [f'{self.locations[0]}{self.keyword_override}']
        else:
            keywords = [
                f'{loc}{ind}'
                for loc in self.locations
                for ind in self.industries
            ]

        self.logger.info(f"启动工商信息爬虫, 模式={self.mode}, 关键词数={len(keywords)}, 已有企业={len(self.seen_credit_codes)}")

        # 存储搜索关键词列表供 async start() 使用
        self._search_keywords = keywords

    async def start(self):
        """Scrapy 2.17 异步 start — yield 带 Playwright meta 的请求

        Scrapy 2.13+ 使用 async def start() 替代 start_requests()。
        此方法 yield 的 Request 可携带任意 meta（如 Playwright 配置），
        不受 start_urls 的 meta 注入限制。
        """
        for kw in self._search_keywords:
            self.stats['search_requests'] += 1
            yield scrapy.Request(
                url=f'{self.GSXT_SEARCH_URL}?search={quote_plus(kw)}',
                callback=self.parse,
                meta={
                    'playwright': True,
                    'playwright_include_page': True,
                    'playwright_page_methods': [],
                    'search_keyword': kw,
                    'max_retries': 3,
                },
                errback=self.errback_search,
                dont_filter=True,
            )

    def closed(self, reason):
        """Spider 关闭时输出统计"""
        self.logger.info(
            f"工商爬虫结束: 搜索请求={self.stats['search_requests']}, "
            f"详情请求={self.stats['detail_requests']}, "
            f"产出={self.stats['items_yielded']}, "
            f"去重跳过={self.stats['items_dropped_dedup']}, "
            f"验证码拦截={self.stats['captcha_encountered']}"
        )

    # ================================================================
    # 页面解析 — 搜索列表页
    # ================================================================

    async def parse(self, response):
        """解析搜索结果列表页"""
        page = response.meta.get('playwright_page')
        keyword = response.meta.get('search_keyword', '')
        max_retries = response.meta.get('max_retries', 3)

        # 从 URL fragment 中恢复 meta 信息 (start_urls 模式)
        if not keyword and '#' in response.url:
            fragment = response.url.split('#')[-1]
            for pair in fragment.split('&'):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    if k == 'search_keyword':
                        from urllib.parse import unquote_plus
                        keyword = unquote_plus(v)
                    elif k == 'max_retries':
                        max_retries = int(v)

        try:
            # 检测验证码页面
            if await self._detect_captcha(page):
                self.stats['captcha_encountered'] += 1
                self.logger.warning(f"遇到验证码: keyword={keyword}")

                if max_retries > 0:
                    # 等待后重试 (验证码需人工或自动处理)
                    import asyncio
                    await asyncio.sleep(5)
                    yield scrapy.Request(
                        url=response.url,
                        callback=self.parse,
                        meta={
                            'playwright': True,
                            'playwright_include_page': True,
                            'playwright_page_methods': [],
                            'search_keyword': keyword,
                            'max_retries': max_retries - 1,
                        },
                        errback=self.errback_search,
                        dont_filter=True,
                    )
                else:
                    self.logger.error(f"验证码重试次数用尽，跳过: keyword={keyword}")
                return

            # 解析搜索结果列表
            companies = await self._parse_search_results(page, keyword)

            if not companies:
                self.logger.info(f"无搜索结果: keyword={keyword}")
                return

            for company in companies:
                credit_code = company.get('credit_code', '')

                # 增量模式: 跳过已入库企业
                if self.mode == 'incremental' and credit_code in self.seen_credit_codes:
                    self.stats['items_dropped_dedup'] += 1
                    continue

                # 进入详情页
                detail_url = company.get('detail_url')
                if detail_url:
                    self.stats['detail_requests'] += 1
                    yield scrapy.Request(
                        url=detail_url,
                        callback=self.parse_detail,
                        meta={
                            'playwright': True,
                            'playwright_include_page': True,
                            'playwright_page_methods': [],
                            'company_basic': company,  # 传递列表页基础信息
                        },
                        errback=self.errback_detail,
                    )
                else:
                    # 列表页信息已足够，直接产出
                    item = self._build_item(company, response.url)
                    if item:
                        self.stats['items_yielded'] += 1
                        yield item

        finally:
            if page and not page.is_closed():
                await page.close()

    async def _parse_search_results(self, page, keyword: str) -> list:
        """从搜索结果页面提取企业列表"""
        companies = []

        try:
            # 方式1: 通过 JavaScript 提取搜索结果 (gsxt 动态渲染)
            results = await page.evaluate('''() => {
                const items = document.querySelectorAll('.search-result-item, .list-item, .search-result');
                const data = [];
                items.forEach(item => {
                    const nameEl = item.querySelector('.company-name, .title, a[href*="corporate"]');
                    const name = nameEl ? nameEl.textContent.trim() : '';
                    const href = nameEl ? nameEl.href : '';
                    // 尝试提取信用代码
                    const codeEl = item.querySelector('.credit-code, .uniscid, [data-code]');
                    const code = codeEl ? codeEl.textContent.trim() : '';
                    if (name) {
                        data.push({ name, href, code });
                    }
                });
                return data;
            }''')

            for r in results:
                name = r.get('name', '').strip()
                if not name:
                    continue
                companies.append({
                    'company_name': name,
                    'credit_code': r.get('code', '').strip() or None,
                    'detail_url': r.get('href') or None,
                    'search_keyword': keyword,
                })

            # 方式2: 如果 JS 提取失败，尝试从 response 文本解析
            if not companies:
                content = await page.content()
                companies = self._parse_search_from_html(content, keyword)

        except Exception as e:
            self.logger.error(f"搜索结果解析失败: keyword={keyword}, error={e}")

        return companies

    def _parse_search_from_html(self, html: str, keyword: str) -> list:
        """从 HTML 文本中提取搜索结果 (备选解析方式)"""
        companies = []

        # 匹配企业名称 (中文公司名模式)
        name_pattern = re.compile(
            r'武汉[^\s<>"\']+(?:有限公司|股份有限公司|集团|工作室|研究院|中心)'
        )
        names = name_pattern.findall(html)
        seen = set()

        for name in names:
            if name in seen:
                continue
            seen.add(name)
            companies.append({
                'company_name': name,
                'credit_code': None,
                'detail_url': None,
                'search_keyword': keyword,
            })

        return companies

    # ================================================================
    # 页面解析 — 企业详情页
    # ================================================================

    async def parse_detail(self, response):
        """解析企业详情页"""
        page = response.meta.get('playwright_page')
        company_basic = response.meta.get('company_basic', {})

        try:
            # 等待详情页数据加载
            import asyncio
            try:
                await page.wait_for_selector(
                    '.detail-info, .company-info, .detail-content',
                    timeout=20000
                )
            except Exception:
                self.logger.debug(f"详情页等待超时: url={response.url}")

            # 通过 JS 提取详情页数据
            detail_data = await page.evaluate('''() => {
                const data = {};

                // 企业名称
                const nameEl = document.querySelector('.company-name, h1, .detail-title');
                if (nameEl) data.company_name = nameEl.textContent.trim();

                // 统一社会信用代码
                const codeEl = document.querySelector('[data-key="uniscid"], .credit-code, .uniscid');
                if (codeEl) data.credit_code = codeEl.textContent.trim();

                // 如果没有专门元素，尝试从页面文本提取
                if (!data.credit_code) {
                    const pageText = document.body.innerText;
                    const codeMatch = pageText.match(/统一社会信用代码[：:]+\\s*([0-9A-HJ-NP-RTUW-Y]{18})/);
                    if (codeMatch) data.credit_code = codeMatch[1];
                }

                // 注册资本
                const capitalEl = document.querySelector('[data-key="regCap"], .regcap, .capital');
                if (capitalEl) data.registered_capital = capitalEl.textContent.trim();

                // 成立日期
                const dateEl = document.querySelector('[data-key="estDate"], .estdate, .established');
                if (dateEl) data.established_date = dateEl.textContent.trim();

                // 法定代表人
                const legalEl = document.querySelector('[data-key="legRep"], .legal-person, .operName');
                if (legalEl) data.legal_representative = legalEl.textContent.trim();

                // 经营范围
                const scopeEl = document.querySelector('[data-key="bizScope"], .business-scope, .opscope');
                if (scopeEl) data.business_scope = scopeEl.textContent.trim();

                // 注册地址
                const addrEl = document.querySelector('[data-key="dom"], .address, .regAddr');
                if (addrEl) data.registered_address = addrEl.textContent.trim();

                return data;
            }''')

            # 合并列表页基础信息和详情页数据
            company_data = {**company_basic, **detail_data}

            item = self._build_item(company_data, response.url)
            if item:
                self.stats['items_yielded'] += 1
                yield item

        except Exception as e:
            self.logger.error(f"详情页解析失败: url={response.url}, error={e}")
        finally:
            if page and not page.is_closed():
                await page.close()

    # ================================================================
    # Item 构建
    # ================================================================

    def _build_item(self, data: dict, source_url: str) -> CompanyItem:
        """从原始数据构建 CompanyItem"""
        company_name = data.get('company_name', '').strip()
        if not company_name:
            return None

        credit_code = data.get('credit_code')
        if credit_code:
            credit_code = credit_code.strip()

        # 提取行业标签
        industry_tags = self._extract_industry_tags(
            data.get('business_scope', '') or ''
        )

        item = CompanyItem()
        item['company_name'] = company_name
        item['credit_code'] = credit_code or None
        item['registered_capital'] = data.get('registered_capital', '').strip() or None
        item['capital_amount'] = None  # 由 StandardizePipeline 计算
        item['established_date'] = data.get('established_date', '').strip() or None
        item['legal_representative'] = data.get('legal_representative', '').strip() or None
        item['business_scope'] = data.get('business_scope', '').strip() or None
        item['registered_address'] = data.get('registered_address', '').strip() or None
        item['status'] = 'raw'  # 由 StandardizePipeline 设置
        item['industry_tags'] = industry_tags
        item['source_url'] = source_url

        return item

    def _extract_industry_tags(self, business_scope: str) -> list:
        """从经营范围提取行业标签"""
        TAG_KEYWORDS = {
            '人工智能': ['人工智能', 'AI', '机器学习', '深度学习', 'NLP'],
            '云计算': ['云计算', '云服务', '云原生', 'SaaS', 'PaaS', 'IaaS'],
            '大数据': ['大数据', '数据分析', '数据挖掘', '数据治理'],
            '软件开发': ['软件开发', '软件设计', '信息系统', '应用软件'],
            '物联网': ['物联网', 'IoT', '传感器', '嵌入式'],
            '网络安全': ['网络安全', '信息安全', '等保'],
            '系统集成': ['系统集成', '信息化建设', '智能化工程'],
        }

        tags = []
        for tag, keywords in TAG_KEYWORDS.items():
            if any(kw in business_scope for kw in keywords):
                tags.append(tag)

        return tags

    # ================================================================
    # 验证码检测
    # ================================================================

    async def _detect_captcha(self, page) -> bool:
        """检测页面是否出现验证码"""
        try:
            captcha_selectors = [
                '.captcha',
                '#captcha',
                '.slider-captcha',
                '.geetest_holder',
                '.nc_wrapper',         # 阿里云滑块
                'iframe[src*="captcha"]',
            ]
            for selector in captcha_selectors:
                element = await page.query_selector(selector)
                if element:
                    return True

            # 检查页面文本
            body_text = await page.evaluate('() => document.body.innerText.substring(0, 500)')
            captcha_keywords = ['验证码', '请拖动滑块', '请完成验证', '安全验证']
            if any(kw in body_text for kw in captcha_keywords):
                return True

        except Exception:
            pass

        return False

    # ================================================================
    # 增量采集: 加载已有 credit_code
    # ================================================================

    def _load_existing_codes(self):
        """从数据库加载已入库的 credit_code 集合"""
        settings = get_project_settings()
        database_url = settings.get('DATABASE_URL')

        if not database_url:
            self.logger.warning("DATABASE_URL 未配置，跳过去重加载")
            return

        try:
            conn = psycopg2.connect(database_url)
            with conn.cursor() as cur:
                cur.execute("SELECT credit_code FROM companies WHERE credit_code IS NOT NULL")
                self.seen_credit_codes = {row[0] for row in cur.fetchall()}
            conn.close()
            self.logger.info(f"加载已有企业 {len(self.seen_credit_codes)} 家")
        except Exception as e:
            self.logger.warning(f"加载已有企业失败: {e}, 将不从数据库去重")

    # ================================================================
    # 错误回调
    # ================================================================

    def errback_search(self, failure):
        """搜索请求错误回调"""
        self.logger.error(f"搜索请求失败: {failure.request.url}, error={failure.value}")

    def errback_detail(self, failure):
        """详情请求错误回调"""
        self.logger.error(f"详情请求失败: {failure.request.url}, error={failure.value}")
