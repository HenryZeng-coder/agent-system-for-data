"""技术能力爬虫 — 企业官网 + GitHub API

采集字段: company_id, company_name, tech_stack, github_org, github_stars,
          tech_blog_url, cloud_provider, has_github_org, has_tech_blog, ai_job_ratio

策略:
1. 从数据库 companies 表读取已入库企业
2. 百度搜索企业官网 → 提取技术栈、技术博客URL、云服务商
3. GitHub API (https://api.github.com) → 搜索组织名、Stars数
4. 从 recruitments 表统计 AI岗位占比
5. yield TechProfileItem

流程:
start_requests() → parse_website_search() → parse_website() → parse_github_search() → parse_github_repos() → yield TechProfileItem
"""

import re
import os
import json
import logging
import psycopg2
from urllib.parse import quote_plus

import scrapy
from scrapy.utils.project import get_project_settings

from wuhan_it_crawler.items import TechProfileItem

logger = logging.getLogger(__name__)


class TechSpider(scrapy.Spider):
    """武汉IT企业技术能力采集 Spider"""

    name = 'tech'
    allowed_domains = []  # 企业官网域名不确定，不过滤

    GITHUB_API_URL = 'https://api.github.com'
    GITEE_API_URL = 'https://gitee.com/api/v5'   # 码云 — 国内开源补充源
    BAIDU_URL = 'https://www.baidu.com/s'

    # ---- 技术栈关键词库 ----
    TECH_KEYWORDS = {
        # 编程语言
        'Python': ['python', 'django', 'flask', 'fastapi'],
        'Java': ['java', 'spring', 'springboot', 'mybatis'],
        'Go': ['golang', 'go语言'],
        'C/C++': ['c++', 'c语言', '嵌入式'],
        'JavaScript': ['javascript', 'node.js', 'react', 'vue', 'angular'],
        'TypeScript': ['typescript', 'ts'],
        'PHP': ['php', 'laravel'],
        'Rust': ['rust'],
        # 技术领域
        'AI/ML': ['人工智能', 'AI', '机器学习', '深度学习', 'NLP', '大模型', 'LLM',
                  '计算机视觉', 'CV', '自然语言处理', 'AIGC', '生成式'],
        '大数据': ['大数据', 'hadoop', 'spark', 'flink', 'kafka', '数据中台', '数据仓库'],
        '云计算': ['云计算', 'kubernetes', 'docker', '微服务', 'devops', '云原生',
                  '容器', 'serverless'],
        '数据库': ['mysql', 'postgresql', 'mongodb', 'redis', 'elasticsearch',
                  'oracle', 'sqlserver', 'tidb', 'oceanbase'],
        '物联网': ['物联网', 'iot', '传感器', '嵌入式', '边缘计算'],
        '网络安全': ['网络安全', '信息安全', '等保', '零信任', '防火墙', '漏洞'],
        '信创': ['信创', '国产化', '自主可控', '鸿蒙', '麒麟', '统信', 'uos',
                '鲲鹏', '欧拉', '达梦', '人大金仓'],
        '区块链': ['区块链', '智能合约', 'web3', '数字人民币'],
        '低代码': ['低代码', '无代码', 'lowcode', '可视化开发'],
        '工业互联网': ['工业互联网', 'mes', 'erp', 'scada', '数字孪生', '工业软件'],
        '移动开发': ['android', 'ios', 'flutter', 'react native', '小程序', 'uniapp'],
    }

    # ---- 云服务商关键词 ----
    CLOUD_KEYWORDS = {
        '阿里云': ['阿里云', 'aliyun', 'alibaba cloud'],
        '腾讯云': ['腾讯云', 'tencent cloud'],
        '华为云': ['华为云', 'huawei cloud'],
        'AWS': ['aws', 'amazon web services'],
        'Azure': ['azure', 'microsoft azure'],
        '百度智能云': ['百度云', '百度智能云'],
        '天翼云': ['天翼云', 'ctyun'],
        '移动云': ['移动云', '移动云计算'],
        '联通云': ['联通云', '沃云'],
        '火山引擎': ['火山引擎', '火山云'],
        '京东云': ['京东云', 'jd cloud'],
        '金山云': ['金山云', 'ksyun'],
    }

    # ---- GitHub 搜索模式 ----
    GITHUB_SEARCH_PATTERNS = [
        '{name}',
        '{name}-tech',
        '{name}inc',
        '{name}io',
    ]

    custom_settings = {
        'CONCURRENT_REQUESTS_PER_DOMAIN': 1,
        'DOWNLOAD_DELAY': 6.5,
        'DOWNLOAD_TIMEOUT': 30,
        'RETRY_TIMES': 3,
        # 百度/官网页面需要浏览器UA, 否则返回反爬页
        'USER_AGENT': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    }

    def __init__(self, mode='incremental', company=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = mode
        self.company_override = company
        self.companies = []
        self.github_headers = {}
        self.stats = {
            'companies_processed': 0,
            'items_yielded': 0,
            'github_found': 0,
            'items_dropped': 0,
        }

        self._load_companies()
        self._setup_github_headers()

    async def start(self):
        """根据企业列表生成搜索请求"""
        if not self.companies:
            self.logger.warning("未找到企业，跳过")
            return

        self.logger.info(f"启动技术能力爬虫, 企业数={len(self.companies)}")

        for company in self.companies:
            cid = company['id']
            name = company['company_name']

            yield scrapy.Request(
                url=f'{self.BAIDU_URL}?wd={quote_plus(name + " 官网")}&rn=5',
                callback=self.parse_website_search,
                meta={
                    'company_id': cid,
                    'company_name': name,
                },
                errback=self.errback_request,
            )

    def closed(self, reason):
        self.logger.info(
            f"技术能力爬虫结束: 处理企业={self.stats['companies_processed']}, "
            f"产出={self.stats['items_yielded']}, "
            f"GitHub发现={self.stats['github_found']}, "
            f"丢弃={self.stats['items_dropped']}"
        )

    # ================================================================
    # 官网搜索解析
    # ================================================================

    def parse_website_search(self, response):
        """解析百度搜索结果，获取官网URL"""
        company_id = response.meta['company_id']
        company_name = response.meta['company_name']

        website_url = None

        # 从搜索结果提取官网URL
        # 百度可能返回反爬非文本响应 (NotSupported)，降级为无官网处理
        try:
            search_results = list(response.css('div.result, div.c-container'))
        except Exception:
            self.logger.warning(f"百度搜索结果解析失败(可能被反爬): {company_name}")
            search_results = []

        for result in search_results:
            title_el = result.css('h3 a, .t a')
            url = title_el.attrib.get('href', '')
            title_text = title_el.css('::text').get('')

            if not url or not title_text:
                continue

            # 排除非官网结果
            skip_domains = ['baike.baidu.com', 'zhihu.com', 'tieba.baidu.com',
                            'job', 'zhipin', 'lagou', '51job']
            if any(d in url.lower() or d in (title_text or '').lower() for d in skip_domains):
                continue

            # 找到第一个看起来像官网的结果
            website_url = url
            break

        if website_url:
            # 进入官网页面提取技术信息
            yield scrapy.Request(
                url=website_url,
                callback=self.parse_website,
                meta={
                    'company_id': company_id,
                    'company_name': company_name,
                },
                errback=self.errback_request,
                dont_filter=True,
            )
        else:
            # 无法找到官网，仍然继续 GitHub 搜索
            short_name = self._shorten_name(company_name)
            yield scrapy.Request(
                url=f'{self.GITHUB_API_URL}/search/users?q={quote_plus(short_name)}&per_page=5',
                callback=self.parse_github_search,
                headers=self.github_headers,
                meta={
                    'company_id': company_id,
                    'company_name': company_name,
                    'short_name': short_name,
                    'tech_stack': [],
                    'cloud_provider': None,
                    'tech_blog_url': None,
                },
                errback=self.errback_request,
            )

    def parse_website(self, response):
        """解析企业官网，提取技术栈、博客URL、云服务商
        先产出 item（官网数据），然后发起 GitHub 搜索来补充更新"""
        company_id = response.meta['company_id']
        company_name = response.meta['company_name']

        page_text = response.css('body').xpath('string(.)').get('')

        # 提取技术栈
        tech_stack = self._extract_tech_stack(page_text)

        # 提取云服务商
        cloud_provider = self._extract_cloud_provider(page_text)

        # 提取技术博客URL
        tech_blog_url = self._extract_tech_blog(response)

        # 先用官网数据产出 item
        self.stats['companies_processed'] += 1
        item = self._build_item(
            company_id=company_id,
            company_name=company_name,
            tech_stack=tech_stack,
            github_org=None,
            github_stars=None,
            tech_blog_url=tech_blog_url,
            cloud_provider=cloud_provider,
        )
        if item:
            self.stats['items_yielded'] += 1
            yield item

        # 发起 GitHub 搜索，将官网数据通过 meta 传递
        short_name = self._shorten_name(company_name)
        yield scrapy.Request(
            url=f'{self.GITHUB_API_URL}/search/users?q={quote_plus(short_name)}&per_page=5',
            callback=self.parse_github_search,
            headers=self.github_headers,
            meta={
                'company_id': company_id,
                'company_name': company_name,
                'short_name': short_name,
                'tech_stack': tech_stack,
                'cloud_provider': cloud_provider,
                'tech_blog_url': tech_blog_url,
            },
            errback=self.errback_request,
            dont_filter=True,
        )

    # ================================================================
    # GitHub 搜索解析
    # ================================================================

    def parse_github_search(self, response):
        """解析 GitHub API 搜索结果"""
        company_id = response.meta['company_id']
        company_name = response.meta['company_name']
        tech_stack = response.meta.get('tech_stack', [])
        cloud_provider = response.meta.get('cloud_provider')
        tech_blog_url = response.meta.get('tech_blog_url')
        short_name = response.meta.get('short_name') or self._shorten_name(company_name)

        try:
            data = json.loads(response.text)
            items = data.get('items', [])

            if items:
                # 取第一个匹配的组织
                org = items[0]
                org_login = org.get('login', '')

                # 获取组织仓库详情
                yield scrapy.Request(
                    url=f'{self.GITHUB_API_URL}/users/{org_login}/repos?per_page=100&sort=stars',
                    callback=self.parse_github_repos,
                    headers=self.github_headers,
                    meta={
                        'company_id': company_id,
                        'company_name': company_name,
                        'github_org': org_login,
                        'tech_stack': tech_stack,
                        'cloud_provider': cloud_provider,
                        'tech_blog_url': tech_blog_url,
                    },
                    errback=self.errback_request,
                )
                self.stats['github_found'] += 1
            else:
                # GitHub 未找到组织 → 补充 Gitee (码云) 搜索
                self.logger.debug(f"GitHub 未找到组织, 尝试 Gitee: {company_name}")
                gitee_headers = {'Accept': 'application/json'}
                gitee_token = os.getenv('GITEE_TOKEN', '')
                if gitee_token:
                    gitee_headers['Authorization'] = f'token {gitee_token}'
                yield scrapy.Request(
                    url=f'{self.GITEE_API_URL}/search/repositories'
                        f'?q={quote_plus(short_name)}&per_page=5',
                    callback=self.parse_gitee_search,
                    headers=gitee_headers,
                    meta={
                        'company_id': company_id,
                        'company_name': company_name,
                        'tech_stack': tech_stack,
                        'cloud_provider': cloud_provider,
                        'tech_blog_url': tech_blog_url,
                    },
                    errback=self.errback_request,
                )

        except json.JSONDecodeError:
            self.logger.warning(f"GitHub 响应解析失败: {company_name}")

    def parse_github_repos(self, response):
        """解析 GitHub 组织的仓库列表，合并数据产出 TechProfileItem"""
        company_id = response.meta['company_id']
        company_name = response.meta['company_name']
        github_org = response.meta['github_org']
        tech_stack = response.meta.get('tech_stack', [])
        cloud_provider = response.meta.get('cloud_provider')
        tech_blog_url = response.meta.get('tech_blog_url')

        try:
            repos = json.loads(response.text)
            total_stars = sum(r.get('stargazers_count', 0) for r in repos)

            # 从 repo 语言分布补充技术栈
            repo_languages = set(r.get('language') for r in repos if r.get('language'))

            self.logger.info(
                f"GitHub: {github_org}, Stars={total_stars}, "
                f"Languages={repo_languages}"
            )

            # 合并官网技术栈与 repo 语言
            tech_stack = list(set(tech_stack) | repo_languages)

            self.stats['companies_processed'] += 1
            item = self._build_item(
                company_id=company_id,
                company_name=company_name,
                tech_stack=tech_stack,
                github_org=github_org,
                github_stars=total_stars,
                tech_blog_url=tech_blog_url,
                cloud_provider=cloud_provider,
            )
            if item:
                self.stats['items_yielded'] += 1
                yield item

        except json.JSONDecodeError:
            self.logger.warning(f"GitHub repos 解析失败: {github_org}")

    # ================================================================
    # Gitee 搜索解析 (国内开源补充源)
    # ================================================================

    def parse_gitee_search(self, response):
        """解析 Gitee API 搜索结果 — GitHub 未命中时的国内补充"""
        company_id = response.meta['company_id']
        company_name = response.meta['company_name']
        tech_stack = response.meta.get('tech_stack', [])
        cloud_provider = response.meta.get('cloud_provider')
        tech_blog_url = response.meta.get('tech_blog_url')

        try:
            data = json.loads(response.text)
            repos = data.get('repositories', []) if isinstance(data, dict) else data

            if repos:
                # 取第一个仓库，聚合 stars 与语言
                total_stars = sum(
                    r.get('stargazers_count', 0) or r.get('stars_count', 0)
                    for r in repos
                )
                repo_languages = set(
                    r.get('language') for r in repos if r.get('language')
                )
                org_login = repos[0].get('owner', {}).get('login') or repos[0].get('full_name', '').split('/')[0]

                # 合并官网技术栈与 repo 语言
                tech_stack = list(set(tech_stack) | repo_languages)

                self.logger.info(
                    f"Gitee: {org_login}, Stars={total_stars}, Languages={repo_languages}"
                )
                github_org = f'gitee:{org_login}'
            else:
                github_org = None
                total_stars = None

            self.stats['companies_processed'] += 1
            item = self._build_item(
                company_id=company_id,
                company_name=company_name,
                tech_stack=tech_stack,
                github_org=github_org,
                github_stars=total_stars,
                tech_blog_url=tech_blog_url,
                cloud_provider=cloud_provider,
            )
            if item:
                self.stats['items_yielded'] += 1
                yield item

        except json.JSONDecodeError:
            self.logger.warning(f"Gitee 响应解析失败: {company_name}")
            # 降级: 用官网数据产出 item
            self.stats['companies_processed'] += 1
            item = self._build_item(
                company_id=company_id,
                company_name=company_name,
                tech_stack=tech_stack,
                github_org=None,
                github_stars=None,
                tech_blog_url=tech_blog_url,
                cloud_provider=cloud_provider,
            )
            if item:
                self.stats['items_yielded'] += 1
                yield item

    # ================================================================
    # Item 构建
    # ================================================================

    def _build_item(self, company_id, company_name, tech_stack,
                    github_org, github_stars, tech_blog_url, cloud_provider):
        """构建 TechProfileItem"""
        item = TechProfileItem()
        item['company_id'] = company_id
        item['company_name'] = company_name
        item['tech_stack'] = tech_stack or []
        item['github_org'] = github_org
        item['github_stars'] = github_stars
        item['tech_blog_url'] = tech_blog_url
        item['cloud_provider'] = cloud_provider
        item['has_github_org'] = github_org is not None
        item['has_tech_blog'] = tech_blog_url is not None
        item['ai_job_ratio'] = self._calc_ai_job_ratio(company_id)

        return item

    # ================================================================
    # 信息提取
    # ================================================================

    def _extract_tech_stack(self, text: str) -> list:
        """从页面文本提取技术栈"""
        text_lower = text.lower()
        found = []
        for tech, keywords in self.TECH_KEYWORDS.items():
            if any(kw.lower() in text_lower for kw in keywords):
                found.append(tech)
        return found

    def _extract_cloud_provider(self, text: str) -> str:
        """从页面文本识别云服务商"""
        text_lower = text.lower()
        for provider, keywords in self.CLOUD_KEYWORDS.items():
            if any(kw.lower() in text_lower for kw in keywords):
                return provider
        return None

    def _extract_tech_blog(self, response) -> str:
        """从页面提取技术博客URL"""
        blog_patterns = [
            'a[href*="blog"]',
            'a[href*="tech"]',
            'a[href*="developer"]',
            'a[href*="engineering"]',
        ]
        for pattern in blog_patterns:
            link = response.css(pattern).attrib.get('href', '')
            if link and link.startswith('http'):
                return link
        return None

    def _calc_ai_job_ratio(self, company_id: int) -> float:
        """从 recruitments 表计算 AI岗位占比"""
        settings = get_project_settings()
        database_url = settings.get('DATABASE_URL')
        if not database_url:
            return 0.0

        AI_JOB_KEYWORDS = ['AI', '人工智能', '机器学习', '深度学习', 'NLP',
                           '算法', '大模型', 'LLM', '数据挖掘', 'CV', '计算机视觉']

        try:
            conn = psycopg2.connect(database_url)
            with conn.cursor() as cur:
                # 总招聘数
                cur.execute(
                    "SELECT count(*) FROM recruitments WHERE company_id = %s",
                    (company_id,),
                )
                total = cur.fetchone()[0] or 0

                if total == 0:
                    conn.close()
                    return 0.0

                # AI 相关招聘数
                like_clauses = ' OR '.join(
                    [f"position_title LIKE %s" for _ in AI_JOB_KEYWORDS]
                )
                params = [company_id] + [f'%{kw}%' for kw in AI_JOB_KEYWORDS]
                cur.execute(
                    f"SELECT count(*) FROM recruitments WHERE company_id = %s AND ({like_clauses})",
                    params,
                )
                ai_count = cur.fetchone()[0] or 0

            conn.close()
            return round(ai_count / total, 2)

        except Exception as e:
            self.logger.debug(f"计算AI岗位占比失败: {e}")
            return 0.0

    # ================================================================
    # 工具方法
    # ================================================================

    def _shorten_name(self, name: str) -> str:
        """缩短企业名用于 GitHub 搜索"""
        # 去掉常见后缀
        for suffix in ['有限公司', '股份有限公司', '有限责任公司', '科技', '信息技术']:
            name = name.replace(suffix, '')
        # 去掉"武汉"
        name = name.replace('武汉', '')
        return name.strip()

    def _setup_github_headers(self):
        """配置 GitHub API 请求头"""
        import os
        token = os.getenv('GITHUB_TOKEN', '')
        self.github_headers = {
            'Accept': 'application/vnd.github.v3+json',
        }
        if token:
            self.github_headers['Authorization'] = f'token {token}'

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
                elif self.mode == 'incremental':
                    # 增量模式: 只处理 status='raw' 的新企业, 避免重爬已评分企业
                    cur.execute(
                        "SELECT id, company_name FROM companies WHERE status = 'raw' ORDER BY id"
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
        """请求错误回调 — 处理 GitHub 搜索失败时仍产出 item"""
        self.logger.error(f"请求失败: {failure.request.url}, error={failure.value}")
        # 如果是 GitHub 搜索请求失败，仍用官网数据产出 item
        meta = failure.request.meta
        if 'tech_stack' in meta or 'company_id' in meta:
            company_id = meta.get('company_id')
            company_name = meta.get('company_name', '')
            # 如果有官网数据，产出 item
            if company_id and (meta.get('tech_stack') or meta.get('cloud_provider') or meta.get('tech_blog_url')):
                self.stats['companies_processed'] += 1
                item = self._build_item(
                    company_id=company_id,
                    company_name=company_name,
                    tech_stack=meta.get('tech_stack', []),
                    github_org=None,
                    github_stars=None,
                    tech_blog_url=meta.get('tech_blog_url'),
                    cloud_provider=meta.get('cloud_provider'),
                )
                if item:
                    self.stats['items_yielded'] += 1
                    yield item
