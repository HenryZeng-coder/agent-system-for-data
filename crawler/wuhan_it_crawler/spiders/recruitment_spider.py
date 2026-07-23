"""招聘信息爬虫 — BOSS直聘 / 拉勾 / 猎聘

采集字段: company_id, company_name, position_title, salary_range,
          salary_min, salary_max, tech_keywords, headcount, source_url, source_name

策略:
1. 多源采集: BOSS直聘为主, 拉勾/猎聘为辅
2. 从数据库 companies 读取企业名称作为搜索关键词
3. 解析薪资范围提取 salary_min, salary_max
4. 从岗位描述提取技术关键词
5. yield RecruitmentItem

注意: BOSS直聘反爬最严，需代理IP轮换+UA随机化+频率控制
"""

import re
import logging
import psycopg2
from urllib.parse import quote_plus

import scrapy
from scrapy.utils.project import get_project_settings

from wuhan_it_crawler.items import RecruitmentItem

logger = logging.getLogger(__name__)


class RecruitmentSpider(scrapy.Spider):
    """武汉IT企业招聘信息采集 Spider"""

    name = 'recruitment'
    allowed_domains = ['zhipin.com', 'lagou.com', 'liepin.com']

    # ---- 搜索源 ----
    BOSS_URL = 'https://www.zhipin.com/web/geek/job'
    LAGOU_URL = 'https://www.lagou.com/zhaopin'
    LIEPIN_URL = 'https://www.liepin.com/zhaopin'

    # ---- 技术关键词库 ----
    TECH_KEYWORDS_LIST = [
        'Python', 'Java', 'Go', 'C++', 'JavaScript', 'TypeScript',
        'React', 'Vue', 'Angular', 'Spring', 'Django', 'Flask',
        'AI', '人工智能', '机器学习', '深度学习', 'NLP', '大模型', 'LLM',
        '云计算', 'Docker', 'Kubernetes', 'DevOps',
        '大数据', 'Spark', 'Hadoop', 'Flink',
        'SQL', 'MySQL', 'Redis', 'MongoDB',
        '算法', '数据挖掘', '数据分析',
    ]

    custom_settings = {
        'CONCURRENT_REQUESTS_PER_DOMAIN': 1,
        'DOWNLOAD_DELAY': 2.0,  # BOSS直聘反爬严
        'DOWNLOAD_TIMEOUT': 30,
        'RETRY_TIMES': 3,
    }

    def __init__(self, company=None, source='boss', *args, **kwargs):
        """
        Args:
            company: 可选，指定企业名
            source: 搜索源 (boss/lagou/liepin/all)
        """
        super().__init__(*args, **kwargs)
        self.company_override = company
        self.source = source
        self.companies = []
        self.stats = {
            'search_requests': 0,
            'items_yielded': 0,
            'items_dropped': 0,
        }

    def start_requests(self):
        """从数据库读取企业列表，生成搜索请求"""
        self._load_companies()

        if not self.companies:
            self.logger.warning("未找到企业，跳过")
            return

        self.logger.info(
            f"启动招聘爬虫, 企业数={len(self.companies)}, 搜索源={self.source}"
        )

        for company in self.companies:
            name = company['company_name']

            # BOSS直聘搜索 (为主)
            if self.source in ('boss', 'all'):
                self.stats['search_requests'] += 1
                yield scrapy.Request(
                    url=f'{self.BOSS_URL}?query={quote_plus(name)}&city=101200100&experience=&page=1',
                    callback=self.parse_boss,
                    meta={
                        'company_id': company['id'],
                        'company_name': name,
                        'page': 1,
                    },
                    errback=self.errback_request,
                )

            # 拉勾搜索 (为辅)
            if self.source in ('lagou', 'all'):
                self.stats['search_requests'] += 1
                yield scrapy.Request(
                    url=f'{self.LAGOU_URL}/{quote_plus(name)}/?city=%E6%AD%A6%E6%B1%89',
                    callback=self.parse_lagou,
                    meta={
                        'company_id': company['id'],
                        'company_name': name,
                    },
                    errback=self.errback_request,
                )

            # 猎聘搜索 (为辅)
            if self.source in ('liepin', 'all'):
                self.stats['search_requests'] += 1
                yield scrapy.Request(
                    url=f'{self.LIEPIN_URL}?key={quote_plus(name)}&city=410',
                    callback=self.parse_liepin,
                    meta={
                        'company_id': company['id'],
                        'company_name': name,
                    },
                    errback=self.errback_request,
                )

    def closed(self, reason):
        self.logger.info(
            f"招聘爬虫结束: 搜索={self.stats['search_requests']}, "
            f"产出={self.stats['items_yielded']}, "
            f"丢弃={self.stats['items_dropped']}"
        )

    # ================================================================
    # BOSS直聘解析
    # ================================================================

    def parse_boss(self, response):
        """解析BOSS直聘搜索结果"""
        company_id = response.meta['company_id']
        company_name = response.meta['company_name']
        page = response.meta.get('page', 1)

        # BOSS直聘职位列表
        jobs = response.css('li.job-card-wrapper, div.job-card-left, li[class*="job"]')

        if not jobs:
            # 尝试备用选择器
            jobs = response.css('div.search-job-result li, div.job-list li')

        for job in jobs:
            try:
                # 岗位名称
                title_el = job.css('.job-name, .job-title, span[class*="job-name"]')
                position_title = (title_el.css('::text').get('') or '').strip()

                # 薪资范围
                salary_el = job.css('.salary, .job-salary, span[class*="salary"]')
                salary_text = (salary_el.css('::text').get('') or '').strip()
                salary_min, salary_max = self._parse_salary(salary_text)

                # 技术关键词 (从岗位描述提取)
                desc_el = job.css('.job-desc, .job-detail, div[class*="desc"]')
                desc_text = (desc_el.css('::text').get('') or '').strip()
                tech_keywords = self._extract_tech_keywords(
                    f'{position_title} {desc_text}'
                )

                # 来源URL
                link_el = job.css('a[href*="job_detail"], a.job-card-left')
                source_url = link_el.attrib.get('href', '')
                if source_url and not source_url.startswith('http'):
                    source_url = f'https://www.zhipin.com{source_url}'

                if not position_title:
                    continue

                item = self._build_item(
                    company_id=company_id,
                    company_name=company_name,
                    position_title=position_title,
                    salary_range=salary_text,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    tech_keywords=tech_keywords,
                    headcount=1,
                    source_url=source_url,
                    source_name='boss',
                )
                if item:
                    self.stats['items_yielded'] += 1
                    yield item

            except Exception as e:
                self.logger.debug(f"BOSS职位解析失败: {e}")
                self.stats['items_dropped'] += 1

        # 翻页 (最多3页)
        if page < 3 and jobs:
            next_page = page + 1
            yield scrapy.Request(
                url=f'{self.BOSS_URL}?query={quote_plus(company_name)}&city=101200100&page={next_page}',
                callback=self.parse_boss,
                meta={
                    'company_id': company_id,
                    'company_name': company_name,
                    'page': next_page,
                },
                errback=self.errback_request,
            )

    # ================================================================
    # 拉勾解析
    # ================================================================

    def parse_lagou(self, response):
        """解析拉勾搜索结果"""
        company_id = response.meta['company_id']
        company_name = response.meta['company_name']

        jobs = response.css('li.list_item, div.position_list_item, div[class*="item"]')

        for job in jobs:
            try:
                position_title = (job.css('.position_name, .p-top a::text, h3::text').get('') or '').strip()
                salary_text = (job.css('.salary, .money::text, span[class*="salary"]::text').get('') or '').strip()
                salary_min, salary_max = self._parse_salary(salary_text)

                desc_text = (job.css('.position_desc, .p-bot::text').get('') or '').strip()
                tech_keywords = self._extract_tech_keywords(f'{position_title} {desc_text}')

                source_url = job.css('a[href]').attrib.get('href', '')

                if not position_title:
                    continue

                item = self._build_item(
                    company_id=company_id,
                    company_name=company_name,
                    position_title=position_title,
                    salary_range=salary_text,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    tech_keywords=tech_keywords,
                    headcount=1,
                    source_url=source_url,
                    source_name='lagou',
                )
                if item:
                    self.stats['items_yielded'] += 1
                    yield item

            except Exception as e:
                self.logger.debug(f"拉勾职位解析失败: {e}")
                self.stats['items_dropped'] += 1

    # ================================================================
    # 猎聘解析
    # ================================================================

    def parse_liepin(self, response):
        """解析猎聘搜索结果"""
        company_id = response.meta['company_id']
        company_name = response.meta['company_name']

        jobs = response.css('li.so-job-item, div.job-detail-box, div[class*="job-item"]')

        for job in jobs:
            try:
                position_title = (job.css('.job-title, .title::text, h3::text').get('') or '').strip()
                salary_text = (job.css('.job-salary, .text-warning::text').get('') or '').strip()
                salary_min, salary_max = self._parse_salary(salary_text)

                desc_text = (job.css('.job-labels, .tags::text').get('') or '').strip()
                tech_keywords = self._extract_tech_keywords(f'{position_title} {desc_text}')

                source_url = job.css('a[href]').attrib.get('href', '')

                if not position_title:
                    continue

                item = self._build_item(
                    company_id=company_id,
                    company_name=company_name,
                    position_title=position_title,
                    salary_range=salary_text,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    tech_keywords=tech_keywords,
                    headcount=1,
                    source_url=source_url,
                    source_name='liepin',
                )
                if item:
                    self.stats['items_yielded'] += 1
                    yield item

            except Exception as e:
                self.logger.debug(f"猎聘职位解析失败: {e}")
                self.stats['items_dropped'] += 1

    # ================================================================
    # Item 构建
    # ================================================================

    def _build_item(self, company_id, company_name, position_title,
                    salary_range, salary_min, salary_max, tech_keywords,
                    headcount, source_url, source_name):
        """构建 RecruitmentItem"""
        position_title = position_title.strip()
        if not position_title:
            return None

        item = RecruitmentItem()
        item['company_id'] = company_id
        item['company_name'] = company_name
        item['position_title'] = position_title
        item['salary_range'] = salary_range.strip() if salary_range else None
        item['salary_min'] = salary_min
        item['salary_max'] = salary_max
        item['tech_keywords'] = tech_keywords
        item['headcount'] = headcount
        item['source_url'] = source_url or None
        item['source_name'] = source_name
        return item

    # ================================================================
    # 薪资解析
    # ================================================================

    def _parse_salary(self, text: str):
        """
        解析薪资范围文本:
        - "15-30K" → (15000, 30000)
        - "8K-12K" → (8000, 12000)
        - "5-8千" → (5000, 8000)
        - "年薪20-40万" → (20000, 40000) 月薪估算
        """
        if not text:
            return None, None

        text = text.strip()

        # K格式: "15-30K" / "8K-12K"
        k_match = re.search(r'(\d+)[Kk]?[-~—到至](\d+)[Kk]', text)
        if k_match:
            return int(k_match.group(1)) * 1000, int(k_match.group(2)) * 1000

        # 千格式: "5-8千" / "5000-8000"
        qian_match = re.search(r'(\d+)[-~—到至](\d+)千', text)
        if qian_match:
            return int(qian_match.group(1)) * 1000, int(qian_match.group(2)) * 1000

        # 纯数字: "5000-8000"
        num_match = re.search(r'(\d+)[-~—到至](\d+)', text)
        if num_match:
            low = int(num_match.group(1))
            high = int(num_match.group(2))
            # 判断是月薪还是年薪
            if low > 100000:  # 年薪
                return round(low / 12), round(high / 12)
            return low, high

        # 万格式: "1.5-3万"
        wan_match = re.search(r'(\d+\.?\d*)[-~—到至](\d+\.?\d*)万', text)
        if wan_match:
            return int(float(wan_match.group(1)) * 10000), int(float(wan_match.group(2)) * 10000)

        return None, None

    # ================================================================
    # 技术关键词提取
    # ================================================================

    def _extract_tech_keywords(self, text: str) -> list:
        """从岗位标题和描述提取技术关键词"""
        found = []
        for kw in self.TECH_KEYWORDS_LIST:
            if kw.lower() in text.lower():
                found.append(kw)
        return found

    # ================================================================
    # 加载企业
    # ================================================================

    def _load_companies(self):
        """从数据库读取企业列表"""
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
            self.logger.error(f"加载企业列表失败: {e}")

    def errback_request(self, failure):
        self.logger.error(f"请求失败: {failure.request.url}, error={failure.value}")
