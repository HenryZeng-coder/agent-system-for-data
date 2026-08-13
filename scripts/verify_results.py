#!/usr/bin/env python3
"""最终结果模型验证 — 评分合理性 + 数据真实性判读

用法: python scripts/verify_results.py [--limit N] [--output PATH]
流程:
1. 读取 individual.csv (最终评级结果)
2. 规则校验 (零模型): 信用代码18位格式/日期合法/非空率/重复
3. 模型校验 (DeepSeek 分批): 每家判定 评分是否合理 + 数据是否真实
   (仅基于给定数据判断, 输出 JSON, 防幻觉)
4. 汇总报告 → data/reports/verification_<ts>.md + 控制台摘要
"""
import os
import re
import csv
import sys
import json
import time
import logging
from datetime import datetime

import requests
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
load_dotenv()

BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
MODEL = "deepseek-v4-flash"
BATCH_SIZE = 3

VALIDATION_PROMPT = """你是一位资深企业数据分析师，负责对武汉IT企业评级系统的最终结果做质检。
对下面的每家企业，基于【仅提供的数据】判断两项：

1. score_check: 评级是否合理？对比 评分/等级 与 企业原始数据(经营范围/技术占比/需求标签)：
   - "合理": 评分与数据匹配
   - "偏高": 数据支撑不了这么高的评分
   - "偏低": 数据明显优于评分
2. data_check: 数据是否真实可信？
   - "可信": 公司名/信用代码/经营范围自洽，符合真实企业特征
   - "存疑": 存在可疑点但无法确认（如经营范围与公司名明显矛盾、信用代码格式异常）
   - "可疑": 明显不真实（如公司名与经营范围完全无关、字段像随机拼凑）
3. 给出依据和风险点，不要编造任何数据中没有的信息。

{companies}

严格输出 JSON 数组（不要 markdown 代码块），每项:
{{"company_name": "...", "score_check": "合理|偏高|偏低", "score_reason": "一句话依据",
  "data_check": "可信|存疑|可疑", "data_reason": "一句话依据", "risk_flags": ["风险点"]}}
"""


def load_individual(path):
    """读取 individual.csv → list[dict]"""
    rows = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows


# ============================================================
# 1. 规则校验 (零模型)
# ============================================================

def rule_check(rows):
    issues = []
    for r in rows:
        flags = []
        code = (r.get("credit_code") or "").strip()
        if not code:
            flags.append("信用代码缺失")
        elif not re.fullmatch(r"[0-9A-Z]{18}", code):
            flags.append(f"信用代码格式异常({code})")
        elif not code.startswith("91"):  # 企业统一社会信用代码前缀 91
            flags.append("信用代码非企业前缀(非91开头)")
        name = r.get("company_name") or ""
        if not name:
            flags.append("公司名缺失")
        scope = r.get("business_scope") or ""
        if not scope:
            flags.append("经营范围缺失")
        if flags:
            issues.append({"company_name": name, "rule_flags": flags})
    return issues


# ============================================================
# 2. 模型校验 (DeepSeek 分批)
# ============================================================

def _call_llm(prompt, timeout=120, retries=3):
    for attempt in range(retries):
        try:
            resp = requests.post(
                f"{BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {os.getenv('DEEPSEEK_API_KEY', '')}",
                         "Content-Type": "application/json"},
                json={"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.1, "max_tokens": 8000,
                      "response_format": {"type": "json_object"}},
                timeout=timeout,
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"].get("content")
                # deepseek-v4-flash 为推理模型: reasoning 吃满 max_tokens 时
                # content 可能为空(finish=length), 视为失败重试
                if not content:
                    logger.warning("200响应但content为空(finish=length, reasoning耗尽预算), 重试")
                    time.sleep(3)
                    continue
                return content
            if resp.status_code == 429:
                wait = min(2 ** attempt, 30)
                logger.warning(f"429限流, 等待{wait}s")
                time.sleep(wait)
                continue
            logger.error(f"API错误 {resp.status_code}: {resp.text[:200]}")
            if resp.status_code >= 500:
                time.sleep(5)
                continue
            return None
        except requests.Timeout:
            print(f"DEBUG timeout attempt={attempt}", flush=True)
            logger.error("API超时")
        except Exception as e:
            print(f"DEBUG exc attempt={attempt}: {type(e).__name__}: {str(e)[:150]}", flush=True)
            logger.error(f"API调用异常: {e}")
        time.sleep(3)
    return None


def _parse_json(text):
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        logger.warning(f"JSON解析失败: {text[:150]}")
        return []


def model_check(rows):
    """分批调用 DeepSeek, 返回 {company_name: verdict}"""
    results = {}
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        sections = []
        for j, r in enumerate(batch):
            sections.append(
                f"[企业{j+1}]\n"
                f"公司名称: {r.get('company_name', '未知')}\n"
                f"统一社会信用代码: {r.get('credit_code', '无')}\n"
                f"行业标签: {r.get('industry_tags', '无')}\n"
                f"经营范围: {(r.get('business_scope') or '无')[:200]}\n"
                f"规则引擎评分: {r.get('rules_score', '-')}分/{r.get('rules_level', '-')}级\n"
                f"DeepSeek评分: {r.get('llm_score', '-')}分/{r.get('llm_level', '-')}级\n"
                f"需求标签: {r.get('demand_tags', '无')}\n"
                f"数据量: 新闻{r.get('news_count', 0)}条/招聘{r.get('recruitment_count', 0)}条/招投标{r.get('bidding_count', 0)}条"
            )
        prompt = VALIDATION_PROMPT.replace("{companies}", "\n\n".join(sections))
        logger.info(f"模型校验批次 {i // BATCH_SIZE + 1}/{(len(rows) + BATCH_SIZE - 1) // BATCH_SIZE}")
        text = _call_llm(prompt)
        if not text:
            logger.error(f"批次失败, 跳过: {[r.get('company_name') for r in batch]}")
            continue
        parsed = _parse_json(text)
        if not parsed:
            # JSON解析失败(可能截断): 重试一次
            logger.warning(f"JSON解析失败, 批次重试: {[r.get('company_name') for r in batch]}")
            time.sleep(2)
            text = _call_llm(prompt)
            parsed = _parse_json(text) if text else []
        for item in parsed:
            name = item.get("company_name")
            if name:
                results[name] = item
        time.sleep(0.5)
    return results


# ============================================================
# 3. 汇总报告
# ============================================================

def build_report(rows, rule_issues, model_results, output_path):
    lines = [
        f"# 全链路结果验证报告 — {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"验证企业数: {len(rows)} 家 | 规则校验问题: {len(rule_issues)} 家 | 模型判定完成: {len(model_results)} 家",
        "",
        "## 一、规则校验（零模型）",
        "",
    ]
    if rule_issues:
        for it in rule_issues:
            lines.append(f"- **{it['company_name']}**: {', '.join(it['rule_flags'])}")
    else:
        lines.append("全部通过（信用代码/名称/经营范围基础检查）")
    lines += ["", "## 二、模型判定（DeepSeek）", ""]

    score_counts = {"合理": 0, "偏高": 0, "偏低": 0}
    data_counts = {"可信": 0, "存疑": 0, "可疑": 0}
    table = []
    for r in rows:
        name = r.get("company_name", "")
        v = model_results.get(name, {})
        sc = v.get("score_check", "-")
        dc = v.get("data_check", "-")
        score_counts[sc] = score_counts.get(sc, 0) + 1
        data_counts[dc] = data_counts.get(dc, 0) + 1
        table.append((name, r.get("rules_level"), r.get("llm_level"), sc, dc,
                      v.get("score_reason", ""), v.get("data_reason", ""),
                      "、".join(v.get("risk_flags", []) or [])))

    lines.append(f"评分合理性: 合理{score_counts['合理']} / 偏高{score_counts['偏高']} / 偏低{score_counts['偏低']} / 未判{len(rows) - sum(score_counts.values())}")
    lines.append(f"数据真实性: 可信{data_counts['可信']} / 存疑{data_counts['存疑']} / 可疑{data_counts['可疑']} / 未判{len(rows) - sum(data_counts.values())}")
    lines += ["", "| 企业 | 规则级 | LLM级 | 评分判定 | 数据判定 | 评分依据 | 数据依据 | 风险点 |", "|------|--------|--------|----------|----------|----------|----------|--------|"]
    for t in table:
        lines.append("| " + " | ".join(str(x) for x in t) + " |")

    # 问题企业汇总
    flagged = [t for t in table if t[3] in ("偏高", "偏低") or t[4] in ("存疑", "可疑") or t[7]]
    lines += ["", "## 三、需关注企业", ""]
    if flagged:
        for t in flagged:
            lines.append(f"- **{t[0]}**: 评分{t[3]}({t[5]}) | 数据{t[4]}({t[6]}) | 风险: {t[7] or '无'}")
    else:
        lines.append("无")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info(f"验证报告: {output_path}")
    return lines, score_counts, data_counts


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="只验证前N家(0=全部)")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    input_path = os.path.join(os.path.dirname(__file__), "..", "data", "reports", "individual.csv")
    if not os.path.isfile(input_path):
        logger.error(f"未找到 {input_path}, 请先运行 export_individual.py")
        sys.exit(1)

    rows = load_individual(input_path)
    if args.limit > 0:
        rows = rows[:args.limit]
    logger.info(f"待验证企业: {len(rows)} 家")

    rule_issues = rule_check(rows)
    logger.info(f"规则校验: {len(rows) - len(rule_issues)}/{len(rows)} 家通过, {len(rule_issues)} 家有标记")

    model_results = model_check(rows)
    logger.info(f"模型判定完成: {len(model_results)}/{len(rows)} 家")

    output_path = args.output or os.path.join(
        os.path.dirname(__file__), "..", "data", "reports",
        f"verification_{datetime.now():%Y%m%d_%H%M%S}.md")
    lines, sc, dc = build_report(rows, rule_issues, model_results, output_path)

    print()
    for line in lines[:6]:
        print(line)
    print(f"\n验证报告: {os.path.abspath(output_path)}")


if __name__ == "__main__":
    main()
