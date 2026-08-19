#!/usr/bin/env python3
"""批量获取5号名录企业信用代码 (统一社会信用代码)

多渠道策略:
1. 必应搜索 \"企业名 统一社会信用代码\" — 提取页面中的18位代码 (91/92开头过滤)
2. 水滴信用 shuidi.cn 站内搜索 — 精确匹配企业详情页
3. 爱企查 aiqicha.baidu.com 搜索页

输出: data/potential_companies/credit_codes_5.csv
用法: python scripts/fetch_credit_codes.py [--limit N]
"""
import os
import re
import csv
import sys
import time
import logging
import requests
from urllib.parse import quote_plus

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
from incremental_crawl_and_score import random_headers

CSV_PATH = os.path.join(PROJECT_ROOT, "data", "potential_companies", "5_smart_manufacturing.csv")
OUT_PATH = os.path.join(PROJECT_ROOT, "data", "potential_companies", "credit_codes_5.csv")

CODE_RE = re.compile(r"^(91|92)\d{6}[0-9A-HJ-NP-RTUW-Y]{10}$")


def search_credit_code_bing(name: str) -> list:
    """必应搜索提取信用代码"""
    found = []
    try:
        url = f"https://www.bing.com/search?q={quote_plus(name + ' 统一社会信用代码')}&count=15"
        resp = requests.get(url, headers=random_headers(), timeout=10)
        for c in set(re.findall(r"[0-9A-HJ-NP-RTUW-Y]{18}", resp.text)):
            if CODE_RE.match(c):
                found.append(c)
    except Exception as e:
        logger.debug(f"必应搜索失败 {name}: {e}")
    return found


def search_credit_code_shuidi(name: str) -> list:
    """水滴信用站内搜索"""
    found = []
    try:
        url = f"https://shuidi.cn/s?q={quote_plus(name)}"
        resp = requests.get(url, headers=random_headers(), timeout=10)
        if resp.status_code == 200:
            for c in set(re.findall(r"[0-9A-HJ-NP-RTUW-Y]{18}", resp.text)):
                if CODE_RE.match(c):
                    found.append(c)
    except Exception as e:
        logger.debug(f"水滴搜索失败 {name}: {e}")
    return found


def search_credit_code_sogou(name: str) -> list:
    """搜狗搜索提取信用代码"""
    found = []
    try:
        url = f"https://www.sogou.com/web?query={quote_plus(name + ' 统一社会信用代码')}"
        resp = requests.get(url, headers=random_headers(), timeout=10, allow_redirects=True)
        if len(resp.text) > 5000:  # 反爬页过滤
            for c in set(re.findall(r"[0-9A-HJ-NP-RTUW-Y]{18}", resp.text)):
                if CODE_RE.match(c):
                    found.append(c)
    except Exception as e:
        logger.debug(f"搜狗搜索失败 {name}: {e}")
    return found


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="只处理前N家(测试用)")
    args = parser.parse_args()

    with open(CSV_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if args.limit > 0:
        rows = rows[:args.limit]

    logger.info(f"待处理企业: {len(rows)} 家")

    results = []
    for i, row in enumerate(rows, 1):
        name = (row.get("company_name") or "").strip()
        if not name:
            continue

        # 三渠道搜索
        codes = search_credit_code_bing(name)
        time.sleep(0.5)
        if not codes:
            codes = search_credit_code_shuidi(name)
        time.sleep(0.5)
        if not codes:
            codes = search_credit_code_sogou(name)
        time.sleep(0.5)

        # 候选去重, 优先91开头(企业法人)
        codes = sorted(set(codes), key=lambda c: (c[:2] != "91", c))
        status = "found" if codes else "missing"
        results.append({"company_name": name, "credit_code": codes[0] if codes else "", "candidates": ";".join(codes[:3]), "status": status})
        logger.info(f"[{i}/{len(rows)}] {name}: {status} {codes[0] if codes else ''}")

    with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["company_name", "credit_code", "candidates", "status"])
        writer.writeheader()
        writer.writerows(results)

    found_n = sum(1 for r in results if r["status"] == "found")
    logger.info(f"完成: 找到 {found_n}/{len(results)} 家 → {OUT_PATH}")


if __name__ == "__main__":
    main()
