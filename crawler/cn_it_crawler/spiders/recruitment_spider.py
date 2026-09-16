"""招聘信息爬虫 — 搜索引擎聚合

采集字段: company_id, company_name, position_title, salary_range,
          salary_min, salary_max, tech_keywords, headcount, source_url, source_name

策略:
1. 使用 WebSearchEngine 搜索 "{地域前缀 + }[企业名] 招聘" 获取招聘信息
   (地域前缀由 config.yaml 的 region 段决定, 全国模式为空)
2. 从搜索结果中提取岗位名称、薪资、技术关键词
3. yield RecruitmentItem

注意: 由于招聘网站反爬严格，改用搜索引擎聚合方式获取公开招聘信息
"""

import re
import logging
import psycopg2
from urllib.parse import quote_plus

import scrapy
from scrapy.utils.project import get_project_settings

from cn_it_crawler.items import RecruitmentItem
from engine.region import Region

logger = logging.getLogger(__name__)


class RecruitmentSpider(scrapy.Spider):
    """全国企业招聘信息采集 Spider — 搜索引擎聚合"""

    name = 'recruitment'
    allowed_domains = []

    # ---- 技术关键词库 ----
    TECH_KEYWORDS_LIST = [
        'Python', 'Java', 'Go', 'C++', 'C#', 'JavaScript', 'TypeScript',
        'React', 'Vue', 'Angular', 'Spring', 'Django', 'Flask', 'FastAPI',
        'Node.js', 'PHP', 'Ruby', 'Rust', 'Swift', 'Kotlin',
        'AI', '人工智能', '机器学习', '深度学习', 'NLP', '大模型', 'LLM',
        '计算机视觉', 'CV', 'AIGC', '生成式', '智能体', 'Agent',
        '云计算', 'Docker', 'Kubernetes', 'DevOps', '云原生', '容器', 'Serverless',
        '大数据', 'Spark', 'Hadoop', 'Flink', 'Kafka', '数据中台', '数据仓库',
        'SQL', 'MySQL', 'Redis', 'MongoDB', 'PostgreSQL', 'Elasticsearch', 'TiDB',
        '算法', '数据挖掘', '数据分析',
        '物联网', 'IoT', '嵌入式', '边缘计算',
        '网络安全', '信息安全', '等保', '渗透测试',
        '信创', '鸿蒙', '麒麟', '国产化', '统信',
        '区块链', 'Web3', '智能合约',
        '低代码', '无代码',
        'Android', 'iOS', 'Flutter', 'React Native', '小程序',
        '测试', '自动化测试', 'QA', '运维', 'SRE', 'DBA',
    ]

    # ---- 招聘相关关键词 ----
    JOB_INDICATORS = [
        '招聘', '招人', '岗位', '职位', '工程师', '开发', '程序员',
        '薪资', '月薪', '年薪', 'K', '万', '实习',
    ]

    custom_settings = {
        'CONCURRENT_REQUESTS_PER_DOMAIN': 2,
        'DOWNLOAD_DELAY': 1.0,
        'DOWNLOAD_TIMEOUT': 30,
        'RETRY_TIMES': 3,
    }

    def __init__(self, mode='incremental', company=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = mode
        self.company_override = company
        self.region = Region.from_settings(get_project_settings())
        self.companies = []
        self.stats = {
            'search_requests': 0,
            'items_yielded': 0,
            'items_dropped': 0,
        }

        self._load_companies()

    async def start(self):
        """根据企业列表生成搜索请求"""
        if not self.companies:
            self.logger.warning("未找到企业，跳过")
            return

        self.logger.info(f"启动招聘爬虫, 企业数={len(self.companies)}")

        # 使用 WebSearchEngine 搜索招聘信息
        try:
            from engine.websearch import WebSearchEngine
            search_engine = WebSearchEngine()
        except ImportError:
            import sys
            sys.path.insert(0, '/Users/henry/Desktop/E-InfoInsight-National')
            from engine.websearch import WebSearchEngine
            search_engine = WebSearchEngine()

        for company in self.companies:
            name = company['company_name']
            company_id = company['id']

            # 搜索 "{地域前缀 + }企业名 招聘"
            query = self.region.query(name, '招聘')
            self.stats['search_requests'] += 1

            try:
                results = search_engine.search(query, limit=10)
                for result in results:
                    title = result.get('title', '')
                    summary = result.get('summary', '')
                    url = result.get('url', '')
                    source = result.get('source', 'unknown')

                    # 从标题和摘要中提取岗位信息
                    text = f'{title} {summary}'
                    if not self._is_job_related(text):
                        continue

                    # 提取岗位名称
                    position_title = self._extract_position_title(text)
                    if not position_title:
                        continue

                    # 提取薪资
                    salary_text = self._extract_salary_text(text)
                    salary_min, salary_max = self._parse_salary(salary_text)

                    # 提取技术关键词
                    tech_keywords = self._extract_tech_keywords(text)

                    item = self._build_item(
                        company_id=company_id,
                        company_name=name,
                        position_title=position_title,
                        salary_range=salary_text,
                        salary_min=salary_min,
                        salary_max=salary_max,
                        tech_keywords=tech_keywords,
                        headcount=1,
                        source_url=url,
                        source_name=f'websearch_{source}',
                    )
                    if item:
                        self.stats['items_yielded'] += 1
                        yield item

            except Exception as e:
                self.logger.error(f"搜索招聘失败: {name}, error={e}")

        self.logger.info(f"招聘搜索完成: 产出={self.stats['items_yielded']}")

        # yield 一个 dummy request 让 spider 不报错
        yield scrapy.Request(
            url='data:,',
            callback=self.parse_dummy,
            dont_filter=True,
        )

    def parse_dummy(self, response):
        """Dummy callback"""
        pass

    def closed(self, reason):
        self.logger.info(
            f"招聘爬虫结束: 搜索={self.stats['search_requests']}, "
            f"产出={self.stats['items_yielded']}, "
            f"丢弃={self.stats['items_dropped']}"
        )

    # ================================================================
    # 岗位信息提取
    # ================================================================

    def _is_job_related(self, text):
        """判断文本是否与招聘相关"""
        return any(kw in text for kw in self.JOB_INDICATORS)

    def _extract_position_title(self, text):
        """从文本中提取岗位名称"""
        # 常见 IT 岗位模式
        job_patterns = [
            r'((?:高级|资深|初级|中级)?(?:前端|后端|全栈|Java|Python|Go|C\+\+|AI|算法|数据|运维|测试|产品|UI|交互|安全|架构|技术|开发|软件|系统|数据库|网络|云|大数据|人工智能|深度学习|机器学习|NLP|计算机)[^\s,，、|/]{0,20}(?:工程师|开发|专家|经理|主管|负责人|架构师|分析师|设计师|专员))',
            r'招聘[：:]\s*([^\s,，、|/]{2,30}(?:工程师|开发|专家|经理|主管|架构师|分析师|设计师|专员))',
            r'([^\s,，、|/]{2,20}(?:工程师|开发|专家|架构师|分析师|设计师|专员))\s*招聘',
        ]
        for pattern in job_patterns:
            m = re.search(pattern, text)
            if m:
                title = m.group(1).strip()
                # 清理标题
                title = re.sub(r'[【】\[\]()]', '', title)
                if len(title) > 3 and len(title) < 30:
                    return title
        return None

    def _extract_salary_text(self, text):
        """从文本中提取薪资文本"""
        # K格式: "15-30K"
        m = re.search(r'(\d+[Kk]?[-~—到至]\d+[Kk])', text)
        if m:
            return m.group(1)
        # 万格式: "1.5-3万"
        m = re.search(r'(\d+\.?\d*[-~—到至]\d+\.?\d*万)', text)
        if m:
            return m.group(1)
        # 纯数字: "8000-15000"
        m = re.search(r'(\d{4,}[-~—到至]\d{4,})', text)
        if m:
            return m.group(1)
        return None

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
        """解析薪资范围文本"""
        if not text:
            return None, None

        text = text.strip()

        # K格式: "15-30K" / "8K-12K"
        k_match = re.search(r'(\d+)[Kk]?[-~—到至](\d+)[Kk]', text)
        if k_match:
            return int(k_match.group(1)) * 1000, int(k_match.group(2)) * 1000

        # 千格式: "5-8千"
        qian_match = re.search(r'(\d+)[-~—到至](\d+)千', text)
        if qian_match:
            return int(qian_match.group(1)) * 1000, int(qian_match.group(2)) * 1000

        # 纯数字: "5000-8000"
        num_match = re.search(r'(\d+)[-~—到至](\d+)', text)
        if num_match:
            low = int(num_match.group(1))
            high = int(num_match.group(2))
            if low > 100000:
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
        self.logger.error(f"请求失败: {failure.request.url}, error={failure.value}")
