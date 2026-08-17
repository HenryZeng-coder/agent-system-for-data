"""工商信息爬虫 — 搜索引擎聚合

采集字段: company_name, credit_code, registered_capital, established_date,
          legal_representative, business_scope, registered_address, industry_tags

策略:
1. 使用 WebSearchEngine 搜索 "[企业名] 工商信息" / "[企业名] 注册资本"
2. 从搜索结果摘要中提取企业基本信息
3. yield CompanyItem

注意: gsxt.gov.cn 和 aiqicha.baidu.com 都有严格反爬，改用搜索引擎聚合
"""

import re
import os
import logging
import psycopg2
from urllib.parse import quote_plus

import scrapy
from scrapy.utils.project import get_project_settings

from wuhan_it_crawler.items import CompanyItem

logger = logging.getLogger(__name__)


class BusinessSpider(scrapy.Spider):
    """武汉IT企业工商信息采集 Spider — 搜索引擎聚合"""

    name = 'business'
    allowed_domains = []

    # ---- 搜索关键词 ----
    locations = ['武汉']
    industries = ['软件开发', '信息技术', '科技', '人工智能', '云计算', '大数据', '数字化']

    custom_settings = {
        'CONCURRENT_REQUESTS': 4,
        'DOWNLOAD_DELAY': 1.0,
        'DOWNLOAD_TIMEOUT': 30,
        'RETRY_TIMES': 3,
    }

    def __init__(self, mode='incremental', keyword=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = mode
        self.keyword_override = keyword
        self.seen_credit_codes = set()
        self.stats = {
            'search_requests': 0,
            'items_yielded': 0,
            'items_dropped_dedup': 0,
        }

        self._load_existing_codes()
        if self.keyword_override:
            keywords = [f'{self.locations[0]}{self.keyword_override}']
        else:
            # 多查询变体: 提升字段提取率 (信用代码/成立日期/法人/地址)
            base_keywords = [
                f'{loc}{ind}'
                for loc in self.locations
                for ind in self.industries
            ]
            query_variants = [
                '工商信息', '统一社会信用代码', '注册资本 成立日期',
                '法定代表人 注册地址',
            ]
            keywords = []
            for base in base_keywords:
                for variant in query_variants:
                    keywords.append(f'{base} {variant}')

        self.logger.info(
            f"启动工商信息爬虫, 模式={self.mode}, 关键词数={len(keywords)}, "
            f"已有企业={len(self.seen_credit_codes)}"
        )
        self._search_keywords = keywords

    async def start(self):
        """搜索企业信息"""
        try:
            import sys
            sys.path.insert(0, '/Users/henry/Desktop/repository/E-InfoInsigth-agent-codes')
            from engine.websearch import WebSearchEngine
            search_engine = WebSearchEngine()
        except ImportError:
            from engine.websearch import WebSearchEngine
            search_engine = WebSearchEngine()

        for kw in self._search_keywords:
            self.stats['search_requests'] += 1
            try:
                results = search_engine.search(f'{kw} 公司 注册资本', limit=10)
                for result in results:
                    title = result.get('title', '')
                    summary = result.get('summary', '')
                    url = result.get('url', '')
                    source = result.get('source', 'unknown')

                    text = f'{title} {summary}'

                    # 从文本中提取企业名
                    company_name = self._extract_company_name(text, kw)
                    if not company_name:
                        continue

                    # 增量模式: 跳过已有企业
                    credit_code = self._extract_credit_code(text)
                    if self.mode == 'incremental' and credit_code and credit_code in self.seen_credit_codes:
                        self.stats['items_dropped_dedup'] += 1
                        continue

                    # 提取其他字段
                    registered_capital = self._extract_capital(text)
                    established_date = self._extract_date(text)
                    legal_representative = self._extract_legal_rep(text)
                    business_scope = self._extract_scope(text)
                    registered_address = self._extract_address(text)

                    # 构建行业标签
                    industry_tags = self._extract_industry_tags(business_scope or kw)

                    item = CompanyItem()
                    item['company_name'] = company_name
                    item['credit_code'] = credit_code
                    item['registered_capital'] = registered_capital
                    item['capital_amount'] = None
                    item['established_date'] = established_date
                    item['legal_representative'] = legal_representative
                    item['business_scope'] = business_scope
                    item['registered_address'] = registered_address
                    item['status'] = 'raw'
                    item['industry_tags'] = industry_tags
                    item['source_url'] = url

                    self.stats['items_yielded'] += 1
                    yield item

            except Exception as e:
                self.logger.error(f"搜索工商信息失败: {kw}, error={e}")

        # yield dummy request
        yield scrapy.Request(url='data:,', callback=self.parse_dummy, dont_filter=True)

    def parse_dummy(self, response):
        pass

    def closed(self, reason):
        self.logger.info(
            f"工商爬虫结束: 搜索={self.stats['search_requests']}, "
            f"产出={self.stats['items_yielded']}, "
            f"去重跳过={self.stats['items_dropped_dedup']}"
        )

    # ================================================================
    # 信息提取
    # ================================================================

    def _extract_company_name(self, text, keyword):
        """从文本中提取企业名称"""
        # 匹配中文公司名
        patterns = [
            r'((?:武汉|湖北)[^\s,，、|/<>"]{2,25}(?:有限公司|股份有限公司|集团|工作室|研究院|中心))',
            r'([^\s,，、|/<>"]{2,20}(?:有限公司|股份有限公司))',
        ]
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                name = m.group(1).strip()
                # 排除明显的非公司名
                exclude = ['搜索', '结果', '推荐', '更多', '百度', '搜狗', '必应', '新闻']
                if any(e in name for e in exclude):
                    continue
                # 清理名称中的噪声字符 (括号残留/特殊符号)
                name = re.sub(r'[()（）\[\]【】<>]', '', name)
                name = re.sub(r'[、，,。|/]', '', name).strip()
                # 清理后仍保留公司后缀才有效
                if name.endswith(('有限公司', '股份有限公司', '集团', '工作室', '研究院', '中心')):
                    return name
        return None

    def _extract_credit_code(self, text):
        """提取统一社会信用代码"""
        m = re.search(r'([0-9A-HJ-NP-RTUW-Y]{18})', text)
        return m.group(1) if m else None

    def _extract_capital(self, text):
        """提取注册资本"""
        m = re.search(r'注册资本[：:为约]\s*([\d.]+[亿万]?元?(?:人民币)?)', text)
        if m:
            return m.group(1)
        m = re.search(r'([\d.]+[亿万]?元?(?:人民币)?)\s*注册资本', text)
        if m:
            return m.group(1)
        return None

    def _extract_date(self, text):
        """提取成立日期"""
        m = re.search(r'成立[日期于：:]+\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?)', text)
        if m:
            return m.group(1).replace('年', '-').replace('月', '-').replace('日', '').replace('/', '-')
        return None

    def _extract_legal_rep(self, text):
        """提取法定代表人"""
        m = re.search(r'法定代表人[：:为]\s*([^\s,，、]{2,10})', text)
        return m.group(1) if m else None

    def _extract_address(self, text):
        """提取注册地址 — 优先匹配 注册地址/住所 前缀, 回退到武汉地址模式"""
        m = re.search(r'(?:注册地址|住所|地址)[：:]\s*([^\s,，。]{6,80})', text)
        if m:
            addr = m.group(1).strip()
            if '武汉' in addr or '湖北' in addr or '市' in addr:
                return addr
        # 回退: 匹配 "武汉市...号" 形式的地址片段
        m = re.search(r'((?:武汉市?|湖北省武汉市?)[^\s,，。]{5,60}?(?:号|路|大道|街|区))', text)
        return m.group(1) if m else None

    def _extract_scope(self, text):
        """提取经营范围"""
        m = re.search(r'经营范围[：:]\s*([^\s]{10,200})', text)
        if m:
            return m.group(1).strip()
        return None

    def _extract_industry_tags(self, business_scope: str) -> list:
        """从经营范围/关键词提取行业标签

        优先使用 config/industry_keywords.yaml 的 industry_tags 分类词库,
        配置缺失时回退到内置 TAG_KEYWORDS。
        """
        tag_map = self._load_tag_keywords()
        if not tag_map:
            return []

        tags = []
        for tag, keywords in tag_map.items():
            if any(kw.lower() in (business_scope or '').lower() for kw in keywords):
                tags.append(tag)

        return tags

    # ---- 行业标签词库: YAML 配置优先, 内置回退 ----
    TAG_KEYWORDS_FALLBACK = {
        '人工智能': ['人工智能', 'AI', '机器学习', '深度学习', 'NLP'],
        '云计算': ['云计算', '云服务', '云原生', 'SaaS', 'PaaS', 'IaaS'],
        '大数据': ['大数据', '数据分析', '数据挖掘', '数据治理'],
        '软件开发': ['软件开发', '软件设计', '信息系统', '应用软件', '编程', '开发'],
        '物联网': ['物联网', 'IoT', '传感器', '嵌入式'],
        '网络安全': ['网络安全', '信息安全', '等保'],
        '系统集成': ['系统集成', '信息化建设', '智能化工程'],
        '信创': ['信创', '国产化', '自主可控', '鸿蒙', '麒麟'],
        '区块链': ['区块链', '智能合约', 'Web3'],
        '工业互联网': ['工业互联网', '工业软件', 'MES', '数字孪生', '边缘计算'],
        '半导体': ['芯片', '集成电路', '半导体', 'IC设计', '光电子', '光纤'],
        '数字创意': ['数字创意', 'AR', 'VR', '元宇宙', '数字人', '游戏'],
    }

    def _load_tag_keywords(self) -> dict:
        """加载行业标签词库: YAML 配置优先, 内置回退"""
        try:
            import yaml
            config_path = os.path.join(
                os.path.dirname(__file__), '..', '..', '..', 'config', 'industry_keywords.yaml'
            )
            if os.path.exists(config_path):
                with open(config_path, encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                tags = data.get('industry_tags')
                if tags:
                    return tags
        except Exception as e:
            self.logger.warning(f"行业标签词库加载失败({e}), 使用内置回退")
        return self.TAG_KEYWORDS_FALLBACK

    # ================================================================
    # 增量采集: 加载已有 credit_code
    # ================================================================

    def _load_existing_codes(self):
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
            self.logger.warning(f"加载已有企业失败: {e}")

    def errback_request(self, failure):
        self.logger.error(f"请求失败: {failure.request.url}, error={failure.value}")
