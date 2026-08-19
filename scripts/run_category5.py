#!/usr/bin/env python3
"""5号企业名录(智能制造)完整爬取流程 — 导入→爬4维→规则评分→DeepSeek→导出

用法: python scripts/run_category5.py [--limit N] [--no-deepseek]
输出: data/potential_companies/5_smart_manufacturing_scored.csv (18列,
      与 all_rated_companies.csv / 1_software_it_services_scored.csv 同格式)
"""
import os
import re
import csv
import sys
import time
import logging
from urllib.parse import quote_plus

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
DATABASE_URL = os.getenv("DATABASE_URL")

CSV_PATH = os.path.join(PROJECT_ROOT, "data", "potential_companies", "5_smart_manufacturing.csv")
OUT_PATH = os.path.join(PROJECT_ROOT, "data", "potential_companies", "5_smart_manufacturing_scored.csv")

OUT_COLUMNS = ["company_name", "credit_code", "registered_capital", "business_scope",
               "industry_tags", "registered_address", "funding_stage",
               "total_score", "rating_level", "tech_score", "funding_score",
               "intent_score", "team_score", "industry_score",
               "demand_tags", "sales_pitch", "reasoning", "crawl_time"]


def parse_capital_amount(text: str) -> float:
    """registered_capital 文本 → 万元数值"""
    if not text:
        return 0.0
    t = text.strip()
    m = re.search(r"([\d.]+)\s*亿美元", t)
    if m:
        return float(m.group(1)) * 10000 * 7.2
    m = re.search(r"([\d.]+)\s*万?美元", t)
    if m:
        return float(m.group(1)) * 7.2
    m = re.search(r"([\d.]+)\s*亿", t)
    if m:
        return float(m.group(1)) * 10000
    m = re.search(r"([\d.]+)\s*万", t)
    if m:
        return float(m.group(1))
    m = re.search(r"([\d.]+)", t)
    if m:
        return float(m.group(1))
    return 0.0


def parse_year(text: str):
    try:
        y = int(str(text).strip())
        if 1900 <= y <= 2026:
            return f"{y}-01-01"
    except (ValueError, TypeError):
        pass
    return None


def import_companies(limit=0):
    """导入 5_smart_manufacturing.csv → companies (status='raw'), 返回导入的(id, name, scope)"""
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if limit > 0:
        rows = rows[:limit]
    logger.info(f"读取 CSV: {len(rows)} 家公司")

    inserted, skipped = 0, 0
    new_companies = []
    with conn.cursor() as cur:
        cur.execute("SELECT company_name FROM companies")
        existing = {r[0] for r in cur.fetchall()}
        for row in rows:
            name = (row.get("company_name") or "").strip()
            if not name or name in existing:
                skipped += 1
                continue
            scope = (row.get("business_scope") or "").strip()
            cap_text = (row.get("registered_capital") or "").strip()
            tags = [t.strip() for t in (row.get("industry_tags") or "").split(",") if t.strip()]
            cur.execute(
                """INSERT INTO companies
                   (company_name, registered_capital, capital_amount,
                    established_date, business_scope, industry_tags, status)
                   VALUES (%s, %s, %s, %s, %s, %s, 'raw') RETURNING id""",
                (name, cap_text, parse_capital_amount(cap_text), parse_year(row.get("established_year")),
                 scope, tags if tags else None),
            )
            new_id = cur.fetchone()[0]
            existing.add(name)
            new_companies.append({"id": new_id, "company_name": name, "business_scope": scope})
            inserted += 1
    conn.commit()
    conn.close()
    logger.info(f"导入完成: 新增 {inserted} 家, 跳过 {skipped} 家")
    return new_companies


def crawl_all(companies):
    """爬4维数据 (复用 incremental_crawl_and_score 的采集函数)

    优化: monkey-patch ics 模块 — 搜索改8s超时+零重试, GitHub 首次失败后
    全局熔断跳过 (原版 SSL 失败被 urllib3 重试3次, 单家可卡30-40分钟)
    """
    import requests as _requests
    from requests.adapters import HTTPAdapter
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
    import incremental_crawl_and_score as ics

    # 零重试 session (SSL/连接错误不重试, 快速失败)
    _session = _requests.Session()
    _session.mount("https://", HTTPAdapter(max_retries=0))
    _session.mount("http://", HTTPAdapter(max_retries=0))

    def _fast_search(url_fn, parser, name, delay=2.0):
        def _search(query, limit=10):
            try:
                time.sleep(delay)
                resp = _session.get(url_fn(query, limit), headers=ics.random_headers(),
                                    timeout=8, allow_redirects=True)
                if len(resp.text) < 5000:  # 反爬/验证页: 快速降级
                    logger.warning(f"{name}搜索疑似反爬(页面过小, {len(resp.text)}B), 降级")
                    return []
                titles = parser(resp.text)
                return [re.sub(r"<[^>]+>", "", t).strip()
                        for t in titles[:limit] if re.sub(r"<[^>]+>", "", t).strip()]
            except Exception as e:
                logger.warning(f"{name}搜索失败(快速降级): {str(e)[:60]}")
                return []
        return _search

    # 替换三个搜索引擎 (解析逻辑与 ics 原版一致, 必应/搜狗用宽松正则)
    ics.search_baidu = _fast_search(
        lambda q, n: f"https://www.baidu.com/s?wd={quote_plus(q)}&rn={n}",
        lambda t: re.findall(r'<h3[^>]*class="[^"]*t[^"]*"[^>]*>.*?<a[^>]*>(.*?)</a>', t, re.DOTALL),
        "百度")
    ics.search_sogou = _fast_search(
        lambda q, n: f"https://www.sogou.com/web?query={quote_plus(q)}&num={n}",
        lambda t: re.findall(r"<h3[^>]*>[\s\S]*?<a[^>]*>([\s\S]*?)</a>", t, re.DOTALL),
        "搜狗")
    ics.search_bing = _fast_search(
        lambda q, n: f"https://www.bing.com/search?q={quote_plus(q)}&count={n}",
        lambda t: re.findall(r"<h2[^>]*>[\s\S]*?<a[^>]*>([\s\S]*?)</a>", t, re.DOTALL),
        "必应")

    # GitHub 熔断: 首次失败后跳过后续所有 GitHub 请求
    state = {"ok": True, "failures": 0}

    def _github_breaker(company_name):
        if not state["ok"]:
            return None, 0
        try:
            short = company_name.replace("武汉", "").replace("有限公司", "").replace("股份", "")
            short = short.replace("科技", "").replace("信息技术", "").replace("(", "").replace(")", "").strip()
            if not short:
                return None, 0
            resp = _session.get(
                f"https://api.github.com/search/users?q={quote_plus(short)}+type:org&per_page=3",
                headers={"Accept": "application/vnd.github.v3+json"}, timeout=8)
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                if items:
                    login = items[0].get("login", "")
                    repos = _session.get(
                        f"https://api.github.com/users/{login}/repos?per_page=100&sort=stargazers",
                        headers={"Accept": "application/vnd.github.v3+json"}, timeout=8)
                    stars = sum(r.get("stargazers_count", 0) for r in repos.json()) if repos.status_code == 200 else 0
                    return login, stars
            return None, 0
        except Exception as e:
            state["failures"] += 1
            logger.warning(f"GitHub搜索失败: {str(e)[:60]}")
            if state["failures"] >= 2:
                state["ok"] = False
                logger.warning("GitHub API 熔断: 后续企业跳过GitHub采集")
            return None, 0

    ics.search_github_org = _github_breaker

    news = ics.crawl_news(companies)
    tech = ics.crawl_tech_profiles(companies)
    rec = ics.crawl_recruitment(companies)
    bid = ics.crawl_bidding(companies)
    logger.info(f"爬取完成: 新闻={news}, 技术画像={tech}, 招聘={rec}, 招投标={bid}")


def score_companies(companies):
    """只对给定企业评分 (参照 batch_score 逻辑, 限定范围)"""
    import psycopg2
    from engine.rules_engine import RatingRulesEngine
    engine = RatingRulesEngine()
    conn = psycopg2.connect(DATABASE_URL)
    passed = failed = 0
    try:
        for company in companies:
            cid = company["id"]
            name = company["company_name"]
            with conn.cursor() as cur:
                cur.execute("SELECT ai_job_ratio, cloud_provider, has_github_org, has_tech_blog "
                            "FROM tech_profiles WHERE company_id = %s", (cid,))
                tech_row = cur.fetchone()
                cur.execute("SELECT COUNT(*) FROM recruitments WHERE company_id = %s", (cid,))
                hiring_count = cur.fetchone()[0]
                cur.execute("SELECT title, content_summary FROM news_mentions WHERE company_id = %s "
                            "ORDER BY published_at DESC LIMIT 5", (cid,))
                news_parts = [" ".join(p for p in (t, s) if p) for t, s in cur.fetchall()]
                cur.execute("SELECT COUNT(*) FROM bidding_records WHERE company_id = %s AND is_digital = TRUE", (cid,))
                has_digital_bid = cur.fetchone()[0] > 0
                cur.execute("SELECT capital_amount, business_scope, industry_tags, funding_stage "
                            "FROM companies WHERE id = %s", (cid,))
                c = cur.fetchone()

            company_data = {
                "company_id": cid, "company_name": name,
                "capital_amount": c[0] or 0,
                "business_scope": c[1] or "",
                "industry_tags": c[2] or [],
                "funding_stage": c[3] or "",
                "ai_job_ratio": tech_row[0] or 0 if tech_row else 0,
                "cloud_provider": tech_row[1] if tech_row else None,
                "has_github_org": bool(tech_row[2]) if tech_row else False,
                "has_tech_blog": bool(tech_row[3]) if tech_row else False,
                "hiring_count": hiring_count,
                "recent_news": " ".join(news_parts),
                "has_digital_bid": has_digital_bid,
            }
            scores = engine.score_company(company_data)
            total, level = scores["total_score"], engine._score_to_level(scores["total_score"])
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO ratings (company_id, total_score, rating_level,
                       tech_score, funding_score, intent_score, team_score, industry_score,
                       rated_by, rated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'rules_engine',NOW())
                       ON CONFLICT (company_id, rated_by) DO UPDATE SET
                       total_score=EXCLUDED.total_score, rating_level=EXCLUDED.rating_level,
                       tech_score=EXCLUDED.tech_score, funding_score=EXCLUDED.funding_score,
                       intent_score=EXCLUDED.intent_score, team_score=EXCLUDED.team_score,
                       industry_score=EXCLUDED.industry_score, rated_at=NOW()""",
                    (cid, total, level, scores["tech_score"], scores["funding_score"],
                     scores["intent_score"], scores["team_score"], scores["industry_score"]),
                )
                cur.execute("UPDATE companies SET status='scored', updated_at=NOW() WHERE id=%s", (cid,))
            logger.info(f"评分: {name} → {total} ({level})")
            if total >= engine.pass_threshold:
                passed += 1
            else:
                failed += 1
        conn.commit()
    finally:
        conn.close()
    logger.info(f"评分完成: 通过{passed}家, 未通过{failed}家")
    return passed, failed


def export_scored(companies, with_deepseek=True):
    """导出18列格式到 5_smart_manufacturing_scored.csv"""
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    names = [c["company_name"] for c in companies]
    with conn.cursor() as cur:
        cur.execute(
            """SELECT c.company_name, c.registered_capital, c.business_scope, c.industry_tags,
                      rr.total_score, rr.rating_level, rr.tech_score, rr.funding_score,
                      rr.intent_score, rr.team_score, rr.industry_score,
                      lr.demand_tags, lr.sales_pitch, lr.reasoning,
                      COALESCE(lr.rated_at, rr.rated_at) AS crawl_time
               FROM companies c
               LEFT JOIN ratings rr ON rr.company_id=c.id AND rr.rated_by='rules_engine'
               LEFT JOIN ratings lr ON lr.company_id=c.id AND lr.rated_by='deepseek'
               WHERE c.company_name = ANY(%s) ORDER BY c.id""",
            (names,),
        )
        rows = cur.fetchall()
    conn.close()

    with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(OUT_COLUMNS)
        for r in rows:
            tags = ", ".join(r[3]) if isinstance(r[3], list) else (r[3] or "")
            demand = ", ".join(r[11]) if isinstance(r[11], list) else (r[11] or "—")
            writer.writerow([
                r[0], "—", r[1] or "—", r[2] or "—", tags or "—", "—", "—",
                r[4] if r[4] is not None else "—",
                r[5] if r[5] else "—",
                r[6] if r[6] is not None else 0, r[7] if r[7] is not None else 0,
                r[8] if r[8] is not None else 0, r[9] if r[9] is not None else 0,
                r[10] if r[10] is not None else 0,
                demand, r[12] or "—", r[13] or "—",
                r[14].strftime("%Y-%m-%d %H:%M:%S") if r[14] else "—",
            ])
    logger.info(f"已导出 {len(rows)} 家 → {OUT_PATH}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="只处理前N家(测试用)")
    parser.add_argument("--no-deepseek", action="store_true", help="跳过DeepSeek评级")
    parser.add_argument("--resume", action="store_true",
                        help="续跑模式: 从数据库取 status='raw' 企业继续处理 (不导入CSV)")
    parser.add_argument("--csv-only", action="store_true",
                        help="resume模式限定为本名录CSV中的企业 (--resume 配合使用)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("5号企业名录(智能制造) 完整爬取流程")
    logger.info("=" * 60)

    if args.resume:
        # 续跑模式: 处理所有 status='raw' 的企业
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        if args.csv_only:
            # 只处理本名录 CSV 中的 raw 企业 (避免连带其他名录)
            with open(CSV_PATH, encoding="utf-8-sig") as f:
                csv_names = {(row.get("company_name") or "").strip()
                             for row in csv.DictReader(f)}
            csv_names.discard("")
            cur = conn.cursor()
            cur.execute(
                "SELECT id, company_name, business_scope FROM companies "
                "WHERE status = 'raw' AND company_name = ANY(%s) ORDER BY id",
                (list(csv_names),))
            companies = [{"id": r[0], "company_name": r[1], "business_scope": r[2]}
                         for r in cur.fetchall()]
            conn.close()
            logger.info(f"续跑模式(本名录CSV限定): {len(companies)} 家 raw 企业")
        else:
            cur = conn.cursor()
            cur.execute("SELECT id, company_name, business_scope FROM companies WHERE status = 'raw' ORDER BY id")
            companies = [{"id": r[0], "company_name": r[1], "business_scope": r[2]} for r in cur.fetchall()]
            conn.close()
            logger.info(f"续跑模式: 数据库 raw 企业 {len(companies)} 家")
        if args.limit > 0:
            companies = companies[:args.limit]
        if not companies:
            logger.info("无 raw 企业需要处理")
            return
    else:
        # 正常模式: 导入CSV新企业
        companies = import_companies(args.limit)
        if not companies:
            logger.info("无新企业可处理(全部已存在或CSV为空)")
            return
        logger.info(f"本次处理企业: {len(companies)} 家")

    # 2. 爬4维
    crawl_all(companies)

    # 3. 规则评分
    passed, failed = score_companies(companies)

    # 4. DeepSeek 评级 (达标企业; get_companies_for_llm 此时只会命中本次scored企业)
    if not args.no_deepseek and passed > 0:
        logger.info("=== DeepSeek 深度评级 ===")
        sys.path.insert(0, PROJECT_ROOT)
        import run_deepseek_rating
        run_deepseek_rating.main()

    # 5. 导出
    export_scored(companies, with_deepseek=not args.no_deepseek)
    logger.info("全部完成")


if __name__ == "__main__":
    main()
