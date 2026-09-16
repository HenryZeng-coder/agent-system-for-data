#!/usr/bin/env python3
"""
补全 status='raw' 企业的工商字段 (默认前 100 家):
business_scope / registered_capital / capital_amount / established_date / credit_code

数据来源 (免费公开):
1. 百度百科 API — 稳定, 含注册资本/成立日期/部分经营范围
2. 必应搜索 "企业名 经营范围" — 从摘要提取经营范围
3. 必应搜索 "企业名 注册资本" — 从摘要提取注册资本

用法: python scripts/enrich_bizinfo.py [--limit N]
"""
import os
import re
import sys
import time
import logging
import psycopg2
import requests
from urllib.parse import quote_plus

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from incremental_crawl_and_score import random_headers  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CODE_RE = re.compile(r"^(91|92)\d{6}[0-9A-HJ-NP-RTUW-Y]{10}$")


def fetch_baike(name: str) -> dict:
    """百度百科 API — 注册资本/成立日期/摘要"""
    url = (f"https://baike.baidu.com/api/openapi/BaikeLemmaCardApi"
           f"?scope=103&format=json&appid=379020&bk_key={quote_plus(name)}&bk_length=600")
    try:
        resp = requests.get(url, headers=random_headers(), timeout=8)
        data = resp.json()
        if not data.get("title"):
            return {}
        info = {}
        card_map = {}
        for item in data.get("card", []):
            if isinstance(item, dict):
                nm = item.get("name", "")
                vals = item.get("value", [])
                if nm and vals:
                    card_map[nm] = vals[0] if isinstance(vals, list) else vals
        abstract = data.get("abstract", "") or ""
        info["abstract"] = abstract

        # 成立日期
        m = re.search(r"成立于(\d{4}年\d{1,2}月\d{1,2}日)", abstract)
        if m:
            info["established"] = m.group(1).replace("年", "-").replace("月", "-").replace("日", "")
        # 注册资本
        m = re.search(r"注册资本[：:为约]?\s*([\d.]+)\s*(亿|万)?\s*(?:元)?(?:人民币)?", abstract)
        if m:
            num = float(m.group(1))
            unit = m.group(2) or "万"
            if unit == "亿":
                info["capital"] = f"{num * 10000:.0f}万元"
            else:
                info["capital"] = f"{num:.0f}万元"
        # 信用代码
        codes = re.findall(r"[0-9A-HJ-NP-RTUW-Y]{18}", abstract + json_dumps(card_map))
        valid = [c for c in set(codes) if CODE_RE.match(c)]
        if valid:
            info["credit_code"] = valid[0]
        return info
    except Exception as e:
        logger.debug(f"baike失败 {name}: {e}")
        return {}


def json_dumps(obj):
    import json
    return json.dumps(obj, ensure_ascii=False)


def bing_snippet(name: str, suffix: str, limit=8) -> str:
    """必应搜索返回摘要文本"""
    try:
        url = f"https://www.bing.com/search?q={quote_plus(name + ' ' + suffix)}&count={limit}"
        resp = requests.get(url, headers=random_headers(), timeout=10)
        text = resp.text
        snippets = []
        blocks = re.findall(r'<li class="b_algo".*?</li>', text, re.DOTALL)
        for b in blocks[:limit]:
            m = re.search(r'<p[^>]*>(.*?)</p>', b, re.DOTALL)
            if m:
                sn = re.sub(r"<[^>]+>", "", m.group(1)).strip()
                if sn:
                    snippets.append(sn)
        return " ".join(snippets)
    except Exception as e:
        logger.debug(f"bing失败 {name}{suffix}: {e}")
        return ""


def extract_scope(snippet: str) -> str:
    """从摘要提取经营范围"""
    m = re.search(r"经营范围[：:]\s*([^。]{10,200})", snippet)
    if m:
        return m.group(1).strip()[:300]
    # 爱企查/水滴摘要常直接给经营范围开头
    m = re.search(r"(?:一般项目|许可项目)[：:]\s*([^。]{10,200})", snippet)
    if m:
        return m.group(1).strip()[:300]
    return ""


def extract_capital(snippet: str) -> str:
    m = re.search(r"注册资本[：:为约]?\s*([\d.]+)\s*(亿|万)?\s*元(?:人民币)?", snippet)
    if m:
        num = float(m.group(1))
        unit = m.group(2) or "万"
        return f"{num * 10000:.0f}万元" if unit == "亿" else f"{num:.0f}万元"
    return ""


def extract_established(snippet: str) -> str:
    m = re.search(r"成立(?:日期|时间)?[：:为约]?\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?)", snippet)
    if m:
        return m.group(1).replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-")
    return ""


def parse_capital_amount(text: str) -> float:
    """万元数值"""
    if not text:
        return 0.0
    m = re.search(r"([\d.]+)\s*亿美元", text)
    if m:
        return float(m.group(1)) * 10000 * 7.2
    m = re.search(r"([\d.]+)\s*亿", text)
    if m:
        return float(m.group(1)) * 10000
    m = re.search(r"([\d.]+)\s*万", text)
    if m:
        return float(m.group(1))
    m = re.search(r"([\d.]+)", text)
    if m:
        return float(m.group(1))
    return 0.0


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    db_url = os.getenv("DATABASE_URL")
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, company_name FROM companies "
            "WHERE (business_scope IS NULL OR business_scope = '') "
            "AND id >= 136 ORDER BY id LIMIT %s",
            (args.limit,),
        )
        companies = cur.fetchall()

    logger.info(f"待补全 {len(companies)} 家")
    updated = 0
    for cid, name in companies:
        scope, capital, established, credit_code = "", "", "", ""

        # 1. 百度百科
        bk = fetch_baike(name)
        time.sleep(0.4)
        capital = bk.get("capital", "")
        established = bk.get("established", "")
        credit_code = bk.get("credit_code", "")

        # 2. 必应搜索经营范围
        sn = bing_snippet(name, "经营范围")
        time.sleep(0.5)
        scope = extract_scope(sn) or ""
        # 摘要无"经营范围:"格式时, 用摘要正文作为经营范围近似 (含行业关键词, 供规则引擎匹配)
        if not scope and sn:
            # 去掉日期/来源噪声, 取前段描述
            cleaned = re.sub(r"\d{4}年\d{1,2}月\d{1,2}日[^。]*", "", sn)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if cleaned and len(cleaned) >= 20:
                scope = cleaned[:300]
        if not capital:
            cap1 = extract_capital(sn)
            capital = cap1 if cap1 else capital
        if not established:
            established = extract_established(sn) or ""

        # 3. 必应搜索注册资本 (仍缺时)
        if not capital:
            sn2 = bing_snippet(name, "注册资本 成立日期")
            time.sleep(0.5)
            if sn2:
                cap2 = extract_capital(sn2)
                capital = cap2 if cap2 else capital
                if not established:
                    established = extract_established(sn2) or ""
                if not scope:
                    scope = extract_scope(sn2) or ""

        cap_amount = parse_capital_amount(capital)
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE companies SET
                       business_scope = COALESCE(NULLIF(%s, ''), business_scope),
                       registered_capital = COALESCE(NULLIF(%s, ''), registered_capital),
                       capital_amount = CASE WHEN %s > 0 THEN %s ELSE capital_amount END,
                       established_date = COALESCE(NULLIF(%s::text, '')::date, established_date),
                       credit_code = COALESCE(NULLIF(%s, ''), credit_code)
                   WHERE id = %s""",
                (scope, capital, cap_amount, cap_amount, established, credit_code, cid),
            )
        updated += 1
        logger.info(f"  [{cid}] {name}: scope={'Y' if scope else 'N'}({len(scope)}字) capital={capital or '-'} est={established or '-'} code={'Y' if credit_code else 'N'}")

    conn.commit()
    conn.close()
    logger.info(f"补全完成: {updated} 家")
    # 汇总
    with psycopg2.connect(db_url) as c2:
        with c2.cursor() as cur:
            cur.execute("SELECT count(*) FROM companies WHERE status='raw' AND business_scope IS NOT NULL AND business_scope != ''")
            print(f"有经营范围: {cur.fetchone()[0]}")
            cur.execute("SELECT count(*) FROM companies WHERE status='raw' AND capital_amount > 0")
            print(f"有注册资本: {cur.fetchone()[0]}")


if __name__ == "__main__":
    main()
