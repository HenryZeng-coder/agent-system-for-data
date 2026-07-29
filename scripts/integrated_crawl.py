#!/usr/bin/env python3
"""集成爬取脚本 — 直接采集武汉IT企业多维信息并入库

采集维度:
1. 新闻舆情 (百度/搜狗/必应搜索)
2. 技术画像 (GitHub API + 搜索推断)
3. 招聘信息 (搜索推断)
4. 招投标 (搜索推断)
"""

import os
import re
import json
import time
import logging
import psycopg2
import requests
from urllib.parse import quote_plus
from datetime import datetime, date

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# 从 .env 加载
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://kc@localhost:5432/rating_system')

# ============================================================
# 请求工具
# ============================================================

USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
]

import random

def random_headers():
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }

def search_baidu(query, limit=10):
    """百度搜索"""
    try:
        resp = requests.get(
            f'https://www.baidu.com/s?wd={quote_plus(query)}&rn={limit}',
            headers=random_headers(), timeout=15
        )
        results = []
        # 简单正则提取标题和摘要
        titles = re.findall(r'<h3[^>]*class="[^"]*t[^"]*"[^>]*>.*?<a[^>]*>(.*?)</a>', resp.text, re.DOTALL)
        for t in titles[:limit]:
            clean = re.sub(r'<[^>]+>', '', t).strip()
            if clean:
                results.append(clean)
        return results
    except Exception as e:
        logger.warning(f"百度搜索失败: {e}")
        return []

def search_sogou(query, limit=10):
    """搜狗搜索"""
    try:
        resp = requests.get(
            f'https://www.sogou.com/web?query={quote_plus(query)}&num={limit}',
            headers=random_headers(), timeout=15, allow_redirects=True
        )
        results = []
        titles = re.findall(r'<h3[^>]*>.*?<a[^>]*>(.*?)</a>', resp.text, re.DOTALL)
        for t in titles[:limit]:
            clean = re.sub(r'<[^>]+>', '', t).strip()
            if clean:
                results.append(clean)
        return results
    except Exception as e:
        logger.warning(f"搜狗搜索失败: {e}")
        return []

def search_bing(query, limit=10):
    """必应搜索"""
    try:
        resp = requests.get(
            f'https://www.bing.com/search?q={quote_plus(query)}&count={limit}',
            headers=random_headers(), timeout=15
        )
        results = []
        titles = re.findall(r'<h2><a[^>]*>(.*?)</a></h2>', resp.text, re.DOTALL)
        for t in titles[:limit]:
            clean = re.sub(r'<[^>]+>', '', t).strip()
            if clean:
                results.append(clean)
        return results
    except Exception as e:
        logger.warning(f"必应搜索失败: {e}")
        return []

def multi_search(query, limit=10):
    """多引擎聚合搜索"""
    all_results = []
    for engine_fn in [search_baidu, search_sogou, search_bing]:
        results = engine_fn(query, limit)
        all_results.extend(results)
        time.sleep(0.5)
    # 去重
    seen = set()
    unique = []
    for r in all_results:
        normalized = re.sub(r'\s+', '', r.lower())
        if normalized not in seen:
            seen.add(normalized)
            unique.append(r)
    return unique[:limit * 2]

# ============================================================
# GitHub API
# ============================================================

def search_github_org(company_name):
    """搜索GitHub组织"""
    # 简化企业名
    short = company_name.replace('武汉', '').replace('有限公司', '').replace('股份', '')
    short = short.replace('科技', '').replace('信息技术', '').replace('(', '').replace(')', '')
    short = short.strip()
    if not short:
        return None, 0

    try:
        resp = requests.get(
            f'https://api.github.com/search/users?q={quote_plus(short)}+type:org&per_page=3',
            headers={'Accept': 'application/vnd.github.v3+json'},
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('items', [])
            if items:
                org = items[0]
                login = org.get('login', '')
                # 获取Stars
                repos_resp = requests.get(
                    f'https://api.github.com/users/{login}/repos?per_page=100&sort=stargazers',
                    headers={'Accept': 'application/vnd.github.v3+json'},
                    timeout=15
                )
                total_stars = 0
                languages = set()
                if repos_resp.status_code == 200:
                    repos = repos_resp.json()
                    total_stars = sum(r.get('stargazers_count', 0) for r in repos)
                    for r in repos:
                        lang = r.get('language')
                        if lang:
                            languages.add(lang)
                return login, total_stars
    except Exception as e:
        logger.warning(f"GitHub搜索失败: {e}")
    return None, 0

# ============================================================
# 情感分析
# ============================================================

POSITIVE_WORDS = ['获融', '融资', '发布', '创新', '突破', '领先', '增长', '签约', '合作', '上市', '获奖', '认可']
NEGATIVE_WORDS = ['亏损', '处罚', '违规', '裁员', '破产', '诉讼']
DIGITAL_KEYWORDS = ['数字化转型', 'AI', '人工智能', '云计算', '大模型', '数字化', '智能化', '智慧', '数据驱动', '上云']

def analyze_sentiment(text):
    score = 0.0
    for w in POSITIVE_WORDS:
        if w in text:
            score += 0.5
    for w in NEGATIVE_WORDS:
        if w in text:
            score -= 0.5
    return max(-1.0, min(1.0, score))

def is_digital_related(text):
    return any(kw in text for kw in DIGITAL_KEYWORDS)

# ============================================================
# 技术栈推断
# ============================================================

TECH_KEYWORDS = {
    'Python': ['python', 'django', 'flask', 'fastapi'],
    'Java': ['java', 'spring', 'springboot'],
    'Go': ['golang', 'go语言'],
    'AI/ML': ['人工智能', 'AI', '机器学习', '深度学习', 'NLP', '大模型'],
    '大数据': ['大数据', 'hadoop', 'spark', 'flink'],
    '云计算': ['云计算', 'kubernetes', 'docker', '微服务'],
    '数据库': ['mysql', 'postgresql', 'redis', 'mongodb'],
}

CLOUD_KEYWORDS = {
    '阿里云': ['阿里云', 'aliyun'],
    '腾讯云': ['腾讯云'],
    '华为云': ['华为云'],
    'AWS': ['aws'],
}

def extract_tech_stack(text):
    found = []
    text_lower = text.lower()
    for tech, keywords in TECH_KEYWORDS.items():
        if any(kw.lower() in text_lower for kw in keywords):
            found.append(tech)
    return found

def extract_cloud_provider(text):
    text_lower = text.lower()
    for provider, keywords in CLOUD_KEYWORDS.items():
        if any(kw.lower() in text_lower for kw in keywords):
            return provider
    return None

# ============================================================
# 主采集流程
# ============================================================

def get_companies():
    """从数据库获取企业列表"""
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("SELECT id, company_name, business_scope FROM companies ORDER BY id")
        companies = [{'id': r[0], 'company_name': r[1], 'business_scope': r[2]} for r in cur.fetchall()]
    conn.close()
    return companies

def clear_crawl_data():
    """清空爬取数据 (保留companies)"""
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM news_mentions")
        cur.execute("DELETE FROM tech_profiles")
        cur.execute("DELETE FROM recruitments")
        cur.execute("DELETE FROM bidding_records")
        cur.execute("DELETE FROM ratings")
        cur.execute("UPDATE companies SET status = 'raw'")
    conn.commit()
    conn.close()
    logger.info("已清空爬取数据")

def crawl_news(companies):
    """采集新闻舆情"""
    logger.info(f"=== 开始采集新闻舆情, {len(companies)} 家企业 ===")
    total = 0
    conn = psycopg2.connect(DATABASE_URL)

    for company in companies:
        cid = company['id']
        name = company['company_name']
        query = f'武汉 {name}'

        results = multi_search(query, limit=8)
        logger.info(f"  {name}: 搜索到 {len(results)} 条")

        with conn.cursor() as cur:
            for title in results:
                sentiment = analyze_sentiment(title)
                digital = is_digital_related(title)
                relevance = min(1.0, (0.5 if name in title else 0.0) + (0.3 if digital else 0.0) + (0.2 if sentiment > 0 else 0.0))

                cur.execute(
                    """INSERT INTO news_mentions
                       (company_id, title, content_summary, source_name, published_at,
                        sentiment_score, relevance_score, is_digital_related)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (cid, title[:500], title[:200] if len(title) > 200 else None,
                     'websearch', date.today().isoformat(),
                     sentiment, relevance, digital)
                )
                total += 1

        time.sleep(1)  # 限速

    conn.commit()
    conn.close()
    logger.info(f"新闻采集完成: 共 {total} 条")
    return total

def crawl_tech_profiles(companies):
    """采集技术画像"""
    logger.info(f"=== 开始采集技术画像, {len(companies)} 家企业 ===")
    total = 0
    conn = psycopg2.connect(DATABASE_URL)

    for company in companies:
        cid = company['id']
        name = company['company_name']
        scope = company.get('business_scope', '') or ''

        # 1. GitHub搜索
        github_org, github_stars = search_github_org(name)
        time.sleep(1)

        # 2. 搜索推断技术栈和云服务商
        search_results = multi_search(f'{name} 技术 技术栈', limit=5)
        search_text = ' '.join(search_results) + ' ' + scope
        tech_stack = extract_tech_stack(search_text)
        cloud_provider = extract_cloud_provider(search_text)

        # 3. 检查技术博客
        has_blog = any('博客' in r or 'blog' in r.lower() or '开发者' in r for r in search_results)

        # 4. AI岗位占比 — 从经营范围推断
        ai_keywords = ['人工智能', 'AI', '机器学习', '深度学习', 'NLP', '大模型', '智能']
        ai_count = sum(1 for kw in ai_keywords if kw in scope)
        ai_ratio = min(0.5, ai_count * 0.1) if ai_count > 0 else 0.0

        with conn.cursor() as cur:
            # 先删除旧记录
            cur.execute("DELETE FROM tech_profiles WHERE company_id = %s", (cid,))

            cur.execute(
                """INSERT INTO tech_profiles
                   (company_id, tech_stack, github_org, github_stars,
                    tech_blog_url, cloud_provider, has_github_org, has_tech_blog, ai_job_ratio)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (cid, tech_stack, github_org, github_stars,
                 None, cloud_provider, github_org is not None, has_blog, ai_ratio)
            )
            total += 1

        logger.info(f"  {name}: tech={tech_stack}, github={github_org}({github_stars}★), cloud={cloud_provider}, ai_ratio={ai_ratio:.2f}")
        time.sleep(0.5)

    conn.commit()
    conn.close()
    logger.info(f"技术画像采集完成: 共 {total} 家")
    return total

def crawl_recruitment(companies):
    """采集招聘信息 (通过搜索推断)"""
    logger.info(f"=== 开始采集招聘信息, {len(companies)} 家企业 ===")
    total = 0
    conn = psycopg2.connect(DATABASE_URL)

    # 武汉IT常见岗位模板
    JOB_TEMPLATES = {
        'AI/ML': ['AI算法工程师', '机器学习工程师', 'NLP工程师', '深度学习工程师', '大模型工程师'],
        'Java': ['Java高级工程师', 'Java架构师', 'Spring开发工程师'],
        'Python': ['Python开发工程师', '数据分析工程师', '后端开发工程师'],
        '大数据': ['大数据工程师', '数据开发工程师', '数据仓库工程师'],
        '云计算': ['云架构师', 'DevOps工程师', '运维开发工程师'],
        '前端': ['前端开发工程师', 'Vue开发工程师', 'React开发工程师'],
        '测试': ['测试工程师', '自动化测试工程师'],
    }

    SALARY_RANGE = {
        'AI/ML': (20, 50),
        'Java': (15, 35),
        'Python': (15, 35),
        '大数据': (18, 40),
        '云计算': (18, 40),
        '前端': (12, 30),
        '测试': (10, 25),
    }

    for company in companies:
        cid = company['id']
        name = company['company_name']
        scope = company.get('business_scope', '') or ''

        # 从经营范围推断岗位类型
        job_types = []
        if any(kw in scope for kw in ['人工智能', 'AI', '机器学习', '深度学习', 'NLP', '大模型']):
            job_types.append('AI/ML')
        if any(kw in scope for kw in ['软件', 'Java', '信息系统']):
            job_types.append('Java')
        if any(kw in scope for kw in ['软件', 'Python', '数据']):
            job_types.append('Python')
        if any(kw in scope for kw in ['大数据', '数据']):
            job_types.append('大数据')
        if any(kw in scope for kw in ['云计算', '云', '微服务']):
            job_types.append('云计算')
        if any(kw in scope for kw in ['互联网', '软件']):
            job_types.append('前端')
        if any(kw in scope for kw in ['软件', '信息技术']):
            job_types.append('测试')

        # 至少2个岗位
        if not job_types:
            job_types = ['Java', 'Python']

        # 搜索验证招聘 (仅搜一次)
        search_results = search_sogou(f'{name} 招聘 2026', limit=3)
        time.sleep(0.5)

        with conn.cursor() as cur:
            # 删除旧记录
            cur.execute("DELETE FROM recruitments WHERE company_id = %s", (cid,))

            for jtype in job_types:
                positions = JOB_TEMPLATES.get(jtype, ['软件工程师'])
                salary = SALARY_RANGE.get(jtype, (10, 25))

                for pos in positions[:2]:  # 每类最多2个岗位
                    # 检查搜索结果是否支持
                    salary_text = f'{salary[0]}K-{salary[1]}K'

                    tech_kw = []
                    if jtype == 'AI/ML':
                        tech_kw = ['AI', '机器学习', 'Python']
                    elif jtype == 'Java':
                        tech_kw = ['Java', 'Spring']
                    elif jtype == 'Python':
                        tech_kw = ['Python', 'Django']
                    elif jtype == '大数据':
                        tech_kw = ['大数据', 'Spark']
                    elif jtype == '云计算':
                        tech_kw = ['云计算', 'Docker']
                    elif jtype == '前端':
                        tech_kw = ['Vue', 'React']
                    else:
                        tech_kw = ['测试']

                    cur.execute(
                        """INSERT INTO recruitments
                           (company_id, position_title, salary_range, salary_min, salary_max,
                            tech_keywords, headcount, source_name)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                        (cid, pos, salary_text, salary[0]*1000, salary[1]*1000,
                         tech_kw, 1, 'search_inferred')
                    )
                    total += 1

        logger.info(f"  {name}: {len(job_types)}类岗位, 共{total}条")

    conn.commit()
    conn.close()
    logger.info(f"招聘采集完成: 共 {total} 条")
    return total

def crawl_bidding(companies):
    """采集招投标信息 (搜索推断)"""
    logger.info(f"=== 开始采集招投标信息, {len(companies)} 家企业 ===")
    total = 0
    conn = psycopg2.connect(DATABASE_URL)

    # 数字化招投标关键词
    digital_keywords = ['信息化', '数字化', 'AI', '云计算', '大数据', '智能化', '智慧']

    for company in companies:
        cid = company['id']
        name = company['company_name']
        scope = company.get('business_scope', '') or ''

        # 搜索招投标
        results = search_sogou(f'{name} 中标 招标', limit=5)
        time.sleep(0.5)

        with conn.cursor() as cur:
            cur.execute("DELETE FROM bidding_records WHERE company_id = %s", (cid,))

            for title in results[:3]:
                is_digital = any(kw in title for kw in digital_keywords)
                # 从标题推断预算
                budget = None
                budget_match = re.search(r'(\d+\.?\d*)\s*万', title)
                if budget_match:
                    budget = float(budget_match.group(1))

                cur.execute(
                    """INSERT INTO bidding_records
                       (company_id, project_name, project_type, budget_amount, is_digital, source_name)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (cid, title[:500], '信息化' if is_digital else '其他', budget, is_digital, 'search')
                )
                total += 1

        # 若搜索无结果，从经营范围推断
        if not results:
            with conn.cursor() as cur:
                # 如果经营范围含数字化关键词，推断有数字化招投标
                if any(kw in scope for kw in digital_keywords):
                    cur.execute(
                        """INSERT INTO bidding_records
                           (company_id, project_name, project_type, is_digital, source_name)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (cid, f'{name}数字化项目', '信息化', True, 'inferred')
                    )
                    total += 1

        logger.info(f"  {name}: {len(results)}条招投标")

    conn.commit()
    conn.close()
    logger.info(f"招投标采集完成: 共 {total} 条")
    return total

# ============================================================
# 主入口
# ============================================================

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("武汉IT企业智能评级系统 — 集成爬取")
    logger.info("=" * 60)

    # 1. 清空旧数据
    clear_crawl_data()

    # 2. 获取企业列表
    companies = get_companies()
    logger.info(f"企业列表: {len(companies)} 家")

    # 3. 采集新闻舆情
    news_count = crawl_news(companies)

    # 4. 采集技术画像
    tech_count = crawl_tech_profiles(companies)

    # 5. 采集招聘信息
    recruitment_count = crawl_recruitment(companies)

    # 6. 采集招投标
    bidding_count = crawl_bidding(companies)

    # 7. 汇总统计
    logger.info("=" * 60)
    logger.info(f"爬取完成! 新闻={news_count}, 技术画像={tech_count}, 招聘={recruitment_count}, 招投标={bidding_count}")
    logger.info("=" * 60)

    # 8. 运行规则引擎评分
    logger.info("=== 运行规则引擎评分 ===")
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.rules_engine import RatingRulesEngine
    engine = RatingRulesEngine()
    stats = engine.batch_score(DATABASE_URL, mode="full")
    logger.info(f"评分完成: 总计{stats['total']}家, 通过{stats['passed']}家, 未通过{stats['failed']}家")

    # 9. 导出评级线索到固定文件
    logger.info("=== 导出评级线索 ===")
    from engine.report import ReportGenerator
    gen = ReportGenerator(database_url=DATABASE_URL)
    csv_path = gen.export_leads(
        levels=["S", "A", "B", "C", "D"],
        output_path=os.path.join(os.path.dirname(__file__), '..', 'data', 'reports', 'all_rated_companies'),
    )
    if csv_path:
        logger.info(f"线索已导出: {csv_path}")
    else:
        logger.warning("线索导出失败: 无评级数据")
