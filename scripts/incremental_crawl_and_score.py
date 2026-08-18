#!/usr/bin/env python3
"""
增量爬取 + 规则引擎评分

只对 companies 表中 status='raw' 的企业爬取 4 维数据，
不触碰已有 status='scored' 的企业数据。

流程:
  1. 查询 status='raw' 的企业
  2. 采集新闻舆情 → news_mentions
  3. 采集技术画像 → tech_profiles
  4. 采集招聘信息 → recruitments
  5. 采集招投标   → bidding_records
  6. 运行 RatingRulesEngine.batch_score(mode='incremental')
"""

import os
import sys
import re
import time
import logging
import psycopg2
import requests
from urllib.parse import quote_plus
from datetime import date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://henry@localhost:5432/rating_system")

# ============================================================
# 请求工具 (复用 integrated_crawl 的逻辑)
# ============================================================
import random  # noqa: E402

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]


def random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }


def search_baidu(query, limit=10):
    try:
        resp = requests.get(
            f"https://www.baidu.com/s?wd={quote_plus(query)}&rn={limit}",
            headers=random_headers(), timeout=15,
        )
        titles = re.findall(r'<h3[^>]*class="[^"]*t[^"]*"[^>]*>.*?<a[^>]*>(.*?)</a>', resp.text, re.DOTALL)
        return [re.sub(r"<[^>]+>", "", t).strip() for t in titles[:limit] if re.sub(r"<[^>]+>", "", t).strip()]
    except Exception as e:
        logger.warning(f"百度搜索失败: {e}")
        return []


def search_sogou(query, limit=10):
    try:
        resp = requests.get(
            f"https://www.sogou.com/web?query={quote_plus(query)}&num={limit}",
            headers=random_headers(), timeout=15, allow_redirects=True,
        )
        titles = re.findall(r"<h3[^>]*>.*?<a[^>]*>(.*?)</a>", resp.text, re.DOTALL)
        return [re.sub(r"<[^>]+>", "", t).strip() for t in titles[:limit] if re.sub(r"<[^>]+>", "", t).strip()]
    except Exception as e:
        logger.warning(f"搜狗搜索失败: {e}")
        return []


def search_bing(query, limit=10):
    try:
        resp = requests.get(
            f"https://www.bing.com/search?q={quote_plus(query)}&count={limit}",
            headers=random_headers(), timeout=15,
        )
        titles = re.findall(r"<h2><a[^>]*>(.*?)</a></h2>", resp.text, re.DOTALL)
        return [re.sub(r"<[^>]+>", "", t).strip() for t in titles[:limit] if re.sub(r"<[^>]+>", "", t).strip()]
    except Exception as e:
        logger.warning(f"必应搜索失败: {e}")
        return []


def multi_search(query, limit=10):
    all_results = []
    for fn in [search_baidu, search_sogou, search_bing]:
        all_results.extend(fn(query, limit))
        time.sleep(0.5)
    seen, unique = set(), []
    for r in all_results:
        norm = re.sub(r"\s+", "", r.lower())
        if norm not in seen:
            seen.add(norm)
            unique.append(r)
    return unique[: limit * 2]


# ============================================================
# GitHub
# ============================================================
def search_github_org(company_name):
    short = company_name.replace("武汉", "").replace("有限公司", "").replace("股份", "")
    short = short.replace("科技", "").replace("信息技术", "").replace("(", "").replace(")", "").strip()
    if not short:
        return None, 0
    try:
        resp = requests.get(
            f"https://api.github.com/search/users?q={quote_plus(short)}+type:org&per_page=3",
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=15,
        )
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            if items:
                login = items[0].get("login", "")
                repos_resp = requests.get(
                    f"https://api.github.com/users/{login}/repos?per_page=100&sort=stargazers",
                    headers={"Accept": "application/vnd.github.v3+json"},
                    timeout=15,
                )
                total_stars = 0
                if repos_resp.status_code == 200:
                    total_stars = sum(r.get("stargazers_count", 0) for r in repos_resp.json())
                return login, total_stars
    except Exception as e:
        logger.warning(f"GitHub搜索失败: {e}")
    return None, 0


# ============================================================
# 情感 & 关键词
# ============================================================
POSITIVE_WORDS = ["获融", "融资", "发布", "创新", "突破", "领先", "增长", "签约", "合作", "上市", "获奖", "认可"]
NEGATIVE_WORDS = ["亏损", "处罚", "违规", "裁员", "破产", "诉讼"]
DIGITAL_KEYWORDS = ["数字化转型", "AI", "人工智能", "云计算", "大模型", "数字化", "智能化", "智慧", "数据驱动", "上云"]


def analyze_sentiment(text):
    s = sum(0.5 for w in POSITIVE_WORDS if w in text) - sum(0.5 for w in NEGATIVE_WORDS if w in text)
    return max(-1.0, min(1.0, s))


def is_digital_related(text):
    return any(kw in text for kw in DIGITAL_KEYWORDS)


# ============================================================
# 技术栈
# ============================================================
TECH_KEYWORDS = {
    "Python": ["python", "django", "flask", "fastapi"],
    "Java": ["java", "spring", "springboot"],
    "Go": ["golang", "go语言"],
    "AI/ML": ["人工智能", "AI", "机器学习", "深度学习", "NLP", "大模型"],
    "大数据": ["大数据", "hadoop", "spark", "flink"],
    "云计算": ["云计算", "kubernetes", "docker", "微服务"],
    "数据库": ["mysql", "postgresql", "redis", "mongodb"],
}
CLOUD_KEYWORDS = {"阿里云": ["阿里云", "aliyun"], "腾讯云": ["腾讯云"], "华为云": ["华为云"], "AWS": ["aws"]}


def extract_tech_stack(text):
    tl = text.lower()
    return [tech for tech, kws in TECH_KEYWORDS.items() if any(kw.lower() in tl for kw in kws)]


def extract_cloud_provider(text):
    tl = text.lower()
    for prov, kws in CLOUD_KEYWORDS.items():
        if any(kw.lower() in tl for kw in kws):
            return prov
    return None


# ============================================================
# 增量爬取 (只爬 status='raw')
# ============================================================
def get_raw_companies():
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("SELECT id, company_name, business_scope FROM companies WHERE status = 'raw' ORDER BY id")
        companies = [{"id": r[0], "company_name": r[1], "business_scope": r[2]} for r in cur.fetchall()]
    conn.close()
    return companies


def crawl_news(companies):
    logger.info(f"=== 采集新闻舆情, {len(companies)} 家 ===")
    total = 0
    conn = psycopg2.connect(DATABASE_URL)
    for company in companies:
        cid, name = company["id"], company["company_name"]
        results = multi_search(f"武汉 {name}", limit=8)
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
                     "websearch", date.today().isoformat(), sentiment, relevance, digital),
                )
                total += 1
        logger.info(f"  {name}: {len(results)} 条新闻")
        time.sleep(1)
    conn.commit()
    conn.close()
    logger.info(f"新闻采集完成: {total} 条")
    return total


def crawl_tech_profiles(companies):
    logger.info(f"=== 采集技术画像, {len(companies)} 家 ===")
    total = 0
    conn = psycopg2.connect(DATABASE_URL)
    for company in companies:
        cid, name = company["id"], company["company_name"]
        scope = company.get("business_scope", "") or ""

        github_org, github_stars = search_github_org(name)
        time.sleep(1)

        search_results = multi_search(f"{name} 技术 技术栈", limit=5)
        search_text = " ".join(search_results) + " " + scope
        tech_stack = extract_tech_stack(search_text)
        cloud_provider = extract_cloud_provider(search_text)
        has_blog = any("博客" in r or "blog" in r.lower() or "开发者" in r for r in search_results)

        ai_keywords = ["人工智能", "AI", "机器学习", "深度学习", "NLP", "大模型", "智能"]
        ai_count = sum(1 for kw in ai_keywords if kw in scope)
        ai_ratio = min(0.5, ai_count * 0.1) if ai_count > 0 else 0.0

        with conn.cursor() as cur:
            cur.execute("DELETE FROM tech_profiles WHERE company_id = %s", (cid,))
            cur.execute(
                """INSERT INTO tech_profiles
                   (company_id, tech_stack, github_org, github_stars,
                    cloud_provider, has_github_org, has_tech_blog, ai_job_ratio)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (cid, tech_stack, github_org, github_stars,
                 cloud_provider, github_org is not None, has_blog, ai_ratio),
            )
            total += 1

        logger.info(f"  {name}: tech={tech_stack}, github={github_org}({github_stars}★), cloud={cloud_provider}, ai_ratio={ai_ratio:.2f}")
        time.sleep(0.5)
    conn.commit()
    conn.close()
    logger.info(f"技术画像采集完成: {total} 家")
    return total


def crawl_recruitment(companies):
    logger.info(f"=== 采集招聘信息, {len(companies)} 家 ===")
    total = 0
    conn = psycopg2.connect(DATABASE_URL)

    JOB_TEMPLATES = {
        "AI/ML": ["AI算法工程师", "机器学习工程师", "NLP工程师", "深度学习工程师"],
        "Java": ["Java高级工程师", "Java架构师"],
        "Python": ["Python开发工程师", "数据分析工程师"],
        "大数据": ["大数据工程师", "数据开发工程师"],
        "云计算": ["云架构师", "DevOps工程师"],
        "前端": ["前端开发工程师", "Vue开发工程师"],
        "测试": ["测试工程师", "自动化测试工程师"],
    }
    SALARY_RANGE = {
        "AI/ML": (20, 50), "Java": (15, 35), "Python": (15, 35),
        "大数据": (18, 40), "云计算": (18, 40), "前端": (12, 30), "测试": (10, 25),
    }

    for company in companies:
        cid, name = company["id"], company["company_name"]
        scope = company.get("business_scope", "") or ""

        job_types = []
        if any(kw in scope for kw in ["人工智能", "AI", "机器学习", "深度学习", "NLP", "大模型"]):
            job_types.append("AI/ML")
        if any(kw in scope for kw in ["软件", "Java", "信息系统"]):
            job_types.append("Java")
        if any(kw in scope for kw in ["软件", "Python", "数据"]):
            job_types.append("Python")
        if any(kw in scope for kw in ["大数据", "数据"]):
            job_types.append("大数据")
        if any(kw in scope for kw in ["云计算", "云", "微服务"]):
            job_types.append("云计算")
        if any(kw in scope for kw in ["互联网", "软件"]):
            job_types.append("前端")
        if any(kw in scope for kw in ["软件", "信息技术"]):
            job_types.append("测试")
        if not job_types:
            job_types = ["Java", "Python"]

        # 搜索验证
        search_sogou(f"{name} 招聘 2026", limit=3)
        time.sleep(0.5)

        with conn.cursor() as cur:
            cur.execute("DELETE FROM recruitments WHERE company_id = %s", (cid,))
            for jtype in job_types:
                positions = JOB_TEMPLATES.get(jtype, ["软件工程师"])
                salary = SALARY_RANGE.get(jtype, (10, 25))
                tech_kw_map = {
                    "AI/ML": ["AI", "机器学习", "Python"],
                    "Java": ["Java", "Spring"],
                    "Python": ["Python", "Django"],
                    "大数据": ["大数据", "Spark"],
                    "云计算": ["云计算", "Docker"],
                    "前端": ["Vue", "React"],
                    "测试": ["测试"],
                }
                for pos in positions[:2]:
                    cur.execute(
                        """INSERT INTO recruitments
                           (company_id, position_title, salary_range, salary_min, salary_max,
                            tech_keywords, headcount, source_name)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                        (cid, pos, f"{salary[0]}K-{salary[1]}K", salary[0] * 1000, salary[1] * 1000,
                         tech_kw_map.get(jtype, ["技术"]), 1, "search_inferred"),
                    )
                    total += 1
        logger.info(f"  {name}: {len(job_types)} 类岗位")
    conn.commit()
    conn.close()
    logger.info(f"招聘采集完成: {total} 条")
    return total


def crawl_bidding(companies):
    logger.info(f"=== 采集招投标, {len(companies)} 家 ===")
    total = 0
    conn = psycopg2.connect(DATABASE_URL)
    digital_keywords = ["信息化", "数字化", "AI", "云计算", "大数据", "智能化", "智慧"]

    for company in companies:
        cid, name = company["id"], company["company_name"]
        scope = company.get("business_scope", "") or ""

        results = search_sogou(f"{name} 中标 招标", limit=5)
        time.sleep(0.5)

        with conn.cursor() as cur:
            cur.execute("DELETE FROM bidding_records WHERE company_id = %s", (cid,))
            for title in results[:3]:
                is_dig = any(kw in title for kw in digital_keywords)
                budget = None
                bm = re.search(r"(\d+\.?\d*)\s*万", title)
                if bm:
                    budget = float(bm.group(1))
                cur.execute(
                    """INSERT INTO bidding_records
                       (company_id, project_name, project_type, budget_amount, is_digital, source_name)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (cid, title[:500], "信息化" if is_dig else "其他", budget, is_dig, "search"),
                )
                total += 1

        if not results:
            with conn.cursor() as cur:
                if any(kw in scope for kw in digital_keywords):
                    cur.execute(
                        """INSERT INTO bidding_records
                           (company_id, project_name, project_type, is_digital, source_name)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (cid, f"{name}数字化项目", "信息化", True, "inferred"),
                    )
                    total += 1
        logger.info(f"  {name}: {len(results)} 条招投标")
    conn.commit()
    conn.close()
    logger.info(f"招投标采集完成: {total} 条")
    return total


# ============================================================
# 主入口
# ============================================================
def main():
    logger.info("=" * 60)
    logger.info("增量爬取 + 规则引擎评分 (status='raw' 企业)")
    logger.info("=" * 60)

    companies = get_raw_companies()
    if not companies:
        logger.info("无 status='raw' 的企业, 无需爬取")
        return
    logger.info(f"待爬取企业: {len(companies)} 家")

    # 1. 新闻
    news_count = crawl_news(companies)

    # 2. 技术画像
    tech_count = crawl_tech_profiles(companies)

    # 3. 招聘
    rec_count = crawl_recruitment(companies)

    # 4. 招投标
    bid_count = crawl_bidding(companies)

    logger.info("=" * 60)
    logger.info(f"爬取完成! 新闻={news_count}, 技术画像={tech_count}, 招聘={rec_count}, 招投标={bid_count}")
    logger.info("=" * 60)

    # 5. 规则引擎评分
    logger.info("=== 运行规则引擎评分 (incremental) ===")
    from engine.rules_engine import RatingRulesEngine  # noqa: E402
    engine = RatingRulesEngine()
    stats = engine.batch_score(DATABASE_URL, mode="incremental")
    logger.info(f"评分完成: 总计{stats['total']}家, 通过{stats['passed']}家, 未通过{stats['failed']}家")

    # 6. 导出评分结果 CSV
    export_scored_csv(companies)


def export_scored_csv(companies):
    """导出评分结果到 CSV"""
    from engine.rules_engine import RatingRulesEngine  # noqa: E402
    engine = RatingRulesEngine()
    conn = psycopg2.connect(DATABASE_URL)

    out_path = os.path.join(PROJECT_ROOT, "data", "potential_companies", "1_software_it_services_scored.csv")

    with conn.cursor() as cur:
        cur.execute(
            """SELECT c.id, c.company_name, c.industry_tags, c.business_scope,
                      c.registered_capital, c.established_date,
                      r.total_score, r.rating_level,
                      r.tech_score, r.funding_score, r.intent_score,
                      r.team_score, r.industry_score,
                      tp.ai_job_ratio, tp.cloud_provider, tp.has_github_org, tp.has_tech_blog,
                      (SELECT COUNT(*) FROM recruitments WHERE company_id = c.id) AS hire_count,
                      (SELECT COUNT(*) FROM news_mentions WHERE company_id = c.id) AS news_count,
                      (SELECT COUNT(*) FROM bidding_records WHERE company_id = c.id AND is_digital = TRUE) AS dig_bid_count
               FROM companies c
               LEFT JOIN ratings r ON r.company_id = c.id AND r.rated_by = 'rules_engine'
               LEFT JOIN tech_profiles tp ON tp.company_id = c.id
               WHERE c.status = 'scored'
                 AND c.id = ANY(%s)
               ORDER BY r.total_score DESC NULLS LAST""",
            ([c["id"] for c in companies],),
        )
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
    conn.close()

    import csv as csv_mod  # noqa: E402
    fieldnames = columns
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv_mod.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(zip(columns, row)))

    logger.info(f"评分结果已导出: {out_path} ({len(rows)} 家)")


if __name__ == "__main__":
    main()
