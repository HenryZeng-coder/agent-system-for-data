#!/usr/bin/env python3
"""第二渠道: 必应搜索定位真实注册名 → 爱企查/水滴信用详情页 → 提取信用代码

对 fetch_biz_info.py 未命中的企业, 用必应搜索:
1. 搜索 \"企业名\" 找到真实注册名 (如 埃斯顿(湖北)机器人工程有限公司)
2. 再搜索真实注册名, 定位 aiqicha/qcc/shuidi 详情页
3. 访问详情页提取信用代码 (百度百科API优先)

输出: data/potential_companies/biz_info_5_v2.csv (增量合并)
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

IN_PATH = os.path.join(PROJECT_ROOT, "data", "potential_companies", "biz_info_5.csv")
OUT_PATH = os.path.join(PROJECT_ROOT, "data", "potential_companies", "biz_info_5_v2.csv")

CODE_RE = re.compile(r"^(91|92)\d{6}[0-9A-HJ-NP-RTUW-Y]{10}$")


def bing_search(name: str, limit=8) -> list:
    """必应搜索返回 (title, href) 列表"""
    results = []
    try:
        url = f"https://www.bing.com/search?q={quote_plus(name)}&count={limit}"
        resp = requests.get(url, headers=random_headers(), timeout=10)
        t = resp.text
        blocks = re.findall(r'<li class="b_algo".*?</li>', t, re.DOTALL)
        for b in blocks[:limit]:
            m = re.search(r'href="([^"]+)"', b)
            tm = re.search(r"<h2[^>]*>(.*?)</h2>", b, re.DOTALL)
            if m:
                title = re.sub(r"<[^>]+>", "", tm.group(1)).strip() if tm else ""
                results.append((title[:80], m.group(1)))
    except Exception as e:
        logger.debug(f"必应失败 {name}: {e}")
    return results


def fetch_baike(name: str) -> dict:
    """百度百科 API (真实注册名查询)"""
    url = (f"https://baike.baidu.com/api/openapi/BaikeLemmaCardApi"
           f"?scope=103&format=json&appid=379020&bk_key={quote_plus(name)}&bk_length=600")
    try:
        resp = requests.get(url, headers=random_headers(), timeout=8)
        data = resp.json()
        if not data.get("title"):
            return None
        info = {"found": True, "source": "baike_v2", "company_name": name, "credit_code": "",
                "legal_rep": "", "address": "", "established": "", "capital": ""}
        card_map = {}
        for item in data.get("card", []):
            if isinstance(item, dict):
                nm = item.get("name", "")
                vals = item.get("value", [])
                if nm and vals:
                    card_map[nm] = vals[0] if isinstance(vals, list) else vals
        info["legal_rep"] = str(card_map.get("法定代表人", "")).strip()[:30]
        info["address"] = str(card_map.get("总部地点", "")).strip()[:120]
        abstract = data.get("abstract", "") or ""
        full_text = abstract + json.dumps(card_map, ensure_ascii=False)
        codes = re.findall(r"[0-9A-HJ-NP-RTUW-Y]{18}", full_text)
        valid = [c for c in set(codes) if CODE_RE.match(c)]
        if valid:
            info["credit_code"] = valid[0]
        return info
    except Exception:
        return None


def main():
    import json
    with open(IN_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    # 只处理未命中的企业
    missing = [r for r in rows if not r.get("credit_code")]
    logger.info(f"总{len(rows)}家, 待补 {len(missing)} 家")

    updated = 0
    for i, row in enumerate(missing, 1):
        name = row["company_name"]
        logger.info(f"[{i}/{len(missing)}] 搜索真实注册名: {name}")

        # 1. 必应搜索找真实注册名
        hits = bing_search(name)
        time.sleep(0.5)

        real_name = None
        for title, href in hits:
            # 标题含完整企业名 (含有限公司等) 且与查询名不同
            if re.search(r"公司|集团|研究院", title) and len(title) > 8:
                # 去重噪音: 跳过明显无关
                if any(k in title for k in ["招聘", "职位", "新闻", "百科", "吧"]):
                    continue
                real_name = title
                break

        # 2. 用真实注册名查百科
        info = None
        if real_name and real_name != name:
            logger.info(f"   真实名: {real_name}")
            info = fetch_baike(real_name)
            time.sleep(0.5)

        if info and info.get("credit_code"):
            row["credit_code"] = info["credit_code"]
            row["legal_rep"] = info.get("legal_rep", "")
            row["address"] = info.get("address", "")
            row["source"] = "baike_v2:" + real_name
            updated += 1
            logger.info(f"   ✓ {name} → {info['credit_code']} (via {real_name})")
        else:
            logger.info(f"   ✗ 仍未找到")

    # 写回 v2 (全量)
    with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        cols = ["company_name", "credit_code", "legal_rep", "address", "established", "capital", "source"]
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in cols})

    logger.info(f"完成: 新增命中 {updated}/{len(missing)} → {OUT_PATH}")


if __name__ == "__main__":
    main()
