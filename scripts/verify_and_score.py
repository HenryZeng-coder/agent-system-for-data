#!/usr/bin/env python3
"""
核验 data/potential_companies/1_software_it_services.csv 的 100 家公司数据，
并用 engine/rules_engine.py 的 RatingRulesEngine 评分。

核验维度:
  1. IT身份过滤 — business_scope 是否命中 scoring_rules.yaml 的 it_filter_keywords
  2. 字段完整性 — company_name / business_scope / registered_capital / established_year 非空
  3. 注册资本格式 — 解析为 capital_amount (万元, 数值); 美元按 7.2 换算
  4. 经营范围合理性 — 非空、长度合理
  5. 成立年份合理性 — 1900 ≤ year ≤ 当前年

评分方式: 离线调用 RatingRulesEngine.score_company(company_data)。
CSV 无 tech_profiles / recruitments / news / bidding 数据, 故这些维度走 0 值,
依赖引擎内置的 scope_tech_fallback / scope_intent / team_fallback 兜底机制评分。
"""

import csv
import os
import re
import sys
from collections import Counter

# 让脚本能 import 项目根目录的 engine 包
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from engine.rules_engine import RatingRulesEngine  # noqa: E402
import yaml  # noqa: E402

CSV_PATH = os.path.join(PROJECT_ROOT, "data", "potential_companies", "1_software_it_services.csv")
SCORING_RULES = os.path.join(PROJECT_ROOT, "config", "scoring_rules.yaml")
OUT_PATH = os.path.join(PROJECT_ROOT, "data", "potential_companies", "1_software_it_services_scored.csv")

USD_TO_RMB = 7.2


def parse_capital(text: str) -> tuple[float, str]:
    """解析注册资本字符串 → (capital_amount 万元, 备注)"""
    if not text:
        return 0.0, "缺失"
    t = text.strip()
    m = re.search(r"([\d.]+)\s*万?美元", t)
    if m:
        amt = float(m.group(1)) * 10000 * USD_TO_RMB / 10000  # 万美元 → 万元
        return amt, f"万美元换算(×{USD_TO_RMB})"
    m = re.search(r"([\d.]+)\s*亿美元", t)
    if m:
        return float(m.group(1)) * 10000 * USD_TO_RMB, "亿美元换算"
    m = re.search(r"([\d.]+)\s*亿元", t)
    if m:
        return float(m.group(1)) * 10000, "亿元→万元"
    m = re.search(r"([\d.]+)\s*万元", t)
    if m:
        return float(m.group(1)), "万元"
    m = re.search(r"([\d.]+)", t)
    if m:
        return float(m.group(1)), "裸数字(假定万元)"
    return 0.0, "无法解析"


def main():
    engine = RatingRulesEngine(SCORING_RULES)
    with open(SCORING_RULES, encoding="utf-8") as f:
        it_keywords = yaml.safe_load(f).get("it_filter_keywords", [])

    with open(CSV_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    print(f"读取 {len(rows)} 家公司: {CSV_PATH}\n")

    results = []
    verify_stats = Counter()
    level_dist = Counter()

    for row in rows:
        name = (row.get("company_name") or "").strip()
        scope = (row.get("business_scope") or "").strip()
        cap_text = (row.get("registered_capital") or "").strip()
        year_text = (row.get("established_year") or "").strip()
        tags = (row.get("industry_tags") or "").strip()

        # ── 核验 ──
        issues = []
        if not name:
            issues.append("公司名缺失")
        if not scope:
            issues.append("经营范围缺失")
        if not cap_text:
            issues.append("注册资本缺失")
        if not year_text:
            issues.append("成立年份缺失")

        # IT 身份过滤
        hit_kw = [kw for kw in it_keywords if kw in scope or kw in tags]
        is_it = len(hit_kw) > 0
        if not is_it:
            issues.append(f"未命中IT过滤词(强信号不足)")

        # 注册资本解析
        capital_amount, cap_note = parse_capital(cap_text)

        # 成立年份合理性
        try:
            year = int(year_text)
            if year < 1900 or year > 2026:
                issues.append(f"成立年份异常({year})")
        except ValueError:
            year = 0
            issues.append(f"成立年份非数字({year_text})")

        verify_stats["total"] += 1
        if issues:
            verify_stats["has_issue"] += 1
            for iss in issues:
                verify_stats[f"issue:{iss.split('(')[0]}"] += 1
        else:
            verify_stats["clean"] += 1
        if is_it:
            verify_stats["it_pass"] += 1
        else:
            verify_stats["it_fail"] += 1

        # ── 构建 company_data, 调用规则引擎评分 ──
        # CSV 无 tech/recruit/news/bidding 数据 → 走兜底机制
        company_data = {
            "company_id": row.get("id"),
            "company_name": name,
            "business_scope": scope,
            "industry_tags": [t.strip() for t in tags.split(",") if t.strip()],
            "capital_amount": capital_amount,
            "funding_stage": "",            # CSV 无融资阶段
            "ai_job_ratio": 0,              # 无 tech_profiles
            "cloud_provider": None,
            "has_github_org": False,
            "has_tech_blog": False,
            "hiring_count": 0,              # 无 recruitments
            "recent_news": "",              # 无 news_mentions
            "has_digital_bid": False,       # 无 bidding_records
        }
        scores = engine.score_company(company_data)
        level = engine._score_to_level(scores["total_score"])
        level_dist[level] += 1

        results.append({
            "id": row.get("id"),
            "company_name": name,
            "industry_tags": tags,
            "business_scope": scope,
            "registered_capital": cap_text,
            "capital_amount_wan": round(capital_amount, 2),
            "established_year": year,
            "it_pass": "是" if is_it else "否",
            "it_keywords_hit": "/".join(hit_kw[:5]),
            "tech_score": scores["tech_score"],
            "funding_score": scores["funding_score"],
            "intent_score": scores["intent_score"],
            "team_score": scores["team_score"],
            "industry_score": scores["industry_score"],
            "total_score": scores["total_score"],
            "rating_level": level,
            "issues": "; ".join(issues) if issues else "",
        })

    # ── 写出评分 CSV ──
    fieldnames = list(results[0].keys())
    with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # ── 打印核验摘要 ──
    print("=" * 60)
    print("一、数据核验摘要")
    print("=" * 60)
    print(f"总公司数:           {verify_stats['total']}")
    print(f"完全合规(clean):    {verify_stats['clean']}")
    print(f"存在问题(has_issue): {verify_stats['has_issue']}")
    print(f"IT身份通过:         {verify_stats['it_pass']}")
    print(f"IT身份未通过:       {verify_stats['it_fail']}")
    print("\n问题分布:")
    for k, v in sorted(verify_stats.items()):
        if k.startswith("issue:"):
            print(f"  {k[6:]:<20} {v}")

    # ── 打印评分摘要 ──
    print("\n" + "=" * 60)
    print("二、评分等级分布 (RatingRulesEngine)")
    print("=" * 60)
    order = ["S", "A", "B", "C", "D"]
    for lvl in order:
        cnt = level_dist.get(lvl, 0)
        bar = "█" * cnt
        print(f"  {lvl}级 (≥{engine.level_thresholds.get(lvl, '?')}): {cnt:>3}  {bar}")
    print(f"\n  通过阈值(B级及以上, ≥{engine.pass_threshold}): "
          f"{sum(level_dist.get(l, 0) for l in ['S', 'A', 'B'])} / {len(results)}")

    # 分数统计
    totals = [r["total_score"] for r in results]
    print(f"\n  总分: 最高 {max(totals)}, 最低 {min(totals)}, "
          f"平均 {sum(totals)/len(totals):.1f}")

    # ── Top10 / Bottom5 ──
    print("\n三、Top 10 (总分最高):")
    print(f"  {'公司名':<32} {'总分':>4} {'等级':>3}  "
          f"tech/fund/intent/team/ind")
    for r in sorted(results, key=lambda x: -x["total_score"])[:10]:
        print(f"  {r['company_name'][:30]:<32} {r['total_score']:>4} {r['rating_level']:>3}  "
              f"{r['tech_score']}/{r['funding_score']}/{r['intent_score']}/"
              f"{r['team_score']}/{r['industry_score']}")

    print("\n四、Bottom 5 (总分最低):")
    for r in sorted(results, key=lambda x: x["total_score"])[:5]:
        issues = f"  ⚠ {r['issues']}" if r["issues"] else ""
        print(f"  {r['company_name'][:30]:<32} {r['total_score']:>4} {r['rating_level']:>3}  "
              f"{r['tech_score']}/{r['funding_score']}/{r['intent_score']}/"
              f"{r['team_score']}/{r['industry_score']}{issues}")

    print(f"\n评分结果已写出: {OUT_PATH}")


if __name__ == "__main__":
    main()
