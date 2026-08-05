"""规则引擎 — 5维度加权评分"""

import yaml
import psycopg2
import logging

logger = logging.getLogger(__name__)


class RatingRulesEngine:
    """5维度规则评分引擎"""

    def __init__(self, config_path="config/scoring_rules.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.level_thresholds = self.config.get("level_thresholds", {
            "S": 80, "A": 60, "B": 40, "C": 20
        })
        self.pass_threshold = self.level_thresholds.get("B", 40)  # B级以上=数字化转型潜在客户

    def score_company(self, company_data: dict) -> dict:
        tech = self._score_tech_investment(company_data)
        funding = self._score_funding(company_data)
        intent = self._score_transformation_intent(company_data)
        team = self._score_team_size(company_data)
        industry = self._score_industry_match(company_data)

        # 跨维度加成：技术强 / 大型成熟技术企业 → 转型意向加成
        intent = self._apply_cross_boost(tech, intent, company_data)

        total = min(tech + funding + intent + team + industry, 100)
        return {
            "total_score": total,
            "tech_score": tech,
            "funding_score": funding,
            "intent_score": intent,
            "team_score": team,
            "industry_score": industry,
            "data_completeness": self._calc_data_completeness(company_data),
        }

    def _calc_data_completeness(self, data: dict) -> dict:
        """评估各维度数据完整度（供 DeepSeek 深度评级参考）"""
        return {
            "tech": 1.0 if (data.get("cloud_provider") or data.get("ai_job_ratio")) else 0.3,
            "funding": 1.0 if data.get("funding_stage") else 0.5,
            "intent": 1.0 if (data.get("recent_news") or data.get("has_digital_bid")) else 0.3,
            "team": 1.0 if (data.get("hiring_count") or 0) >= 5 else 0.3,
            "industry": 1.0,
        }

    def _score_tech_investment(self, data: dict) -> int:
        score = 0
        rules = self.config.get("tech_investment", {}).get("rules", {})
        ai_rule = rules.get("ai_job_ratio", {})
        threshold = ai_rule.get("threshold", 0.2)
        comparison = ai_rule.get("comparison", ">=")
        ai_ratio = data.get("ai_job_ratio", 0)
        if comparison == ">=" and ai_ratio >= threshold:
            score += ai_rule.get("score", 15)
        elif comparison == ">" and ai_ratio > threshold:
            score += ai_rule.get("score", 15)

        if data.get("cloud_provider"):
            score += rules.get("cloud_provider", {}).get("score", 5)
        if data.get("has_github_org"):
            score += rules.get("github_org", {}).get("score", 5)
        if data.get("has_tech_blog"):
            score += rules.get("tech_blog", {}).get("score", 5)

        # 经营范围兜底
        score = self._apply_scope_tech_fallback(data, score)

        return min(score, 30)

    def _apply_scope_tech_fallback(self, data: dict, data_driven_score: int) -> int:
        """数据驱动分低时，用经营范围推断技术投入下限"""
        fb = self.config.get("tech_investment", {}).get("scope_tech_fallback", {})
        if not fb.get("enabled"):
            return data_driven_score
        scope = data.get("business_scope", "") or ""
        tech_min = 0
        for rule in fb.get("rules", []):
            if any(kw in scope for kw in rule.get("keywords", [])):
                tech_min = max(tech_min, rule.get("tech_min", 0))
        return max(data_driven_score, tech_min)

    def _score_funding(self, data: dict) -> int:
        score = 0
        rules = self.config.get("funding", {}).get("rules", {})
        stage = data.get("funding_stage", "")
        stage_scores = rules.get("funding_stage", {})
        if stage in stage_scores:
            score += stage_scores[stage]
        capital_rule = rules.get("registered_capital", {})
        if (data.get("capital_amount") or 0) >= capital_rule.get("threshold", 1000):
            score += capital_rule.get("score", 5)
        # 注册资本梯度加分（取最高匹配档）
        capital = data.get("capital_amount") or 0
        for tier in sorted(rules.get("capital_scale", []), key=lambda x: x.get("threshold", 0), reverse=True):
            if capital >= tier.get("threshold", 0):
                score += tier.get("score", 0)
                break
        cap = self.config.get("funding", {}).get("weight", 25)
        return min(score, cap)

    def _score_transformation_intent(self, data: dict) -> int:
        score = 0
        rules = self.config.get("transformation_intent", {}).get("rules", {})
        keywords = rules.get("news_keywords", [])
        score_per = rules.get("score_per_match", 5)
        max_score = rules.get("max_score", 15)
        recent_news = data.get("recent_news", "") or ""
        matched = sum(1 for kw in keywords if kw in recent_news)
        score += min(matched * score_per, max_score)
        if data.get("has_digital_bid"):
            score += rules.get("digital_bidding", {}).get("score", 10)

        # 经营范围推断转型意向
        scope_intent_config = self.config.get("transformation_intent", {}).get("scope_intent", {})
        if scope_intent_config.get("enabled"):
            scope = data.get("business_scope", "") or ""
            for rule in scope_intent_config.get("rules", []):
                if any(kw in scope for kw in rule.get("keywords", [])):
                    score += rule.get("score", 0)

        cap = self.config.get("transformation_intent", {}).get("weight", 30)
        return min(score, cap)

    def _apply_cross_boost(self, tech_score: int, intent_score: int, data: dict) -> int:
        """跨维度加成：技术投入高 / 大型成熟技术企业 → 转型意向加成"""
        cb = self.config.get("transformation_intent", {}).get("cross_boost", {})
        # 技术强 → 转型意向高
        if tech_score >= cb.get("tech_threshold", 25):
            intent_score += cb.get("intent_bonus", 5)
        # 大型成熟技术企业有转型需求
        ctb = cb.get("capital_tech_boost", {})
        capital = data.get("capital_amount") or 0
        if (capital >= ctb.get("capital_threshold", 5000)
                and tech_score >= ctb.get("tech_threshold", 10)):
            intent_score += ctb.get("intent_bonus", 5)
        cap = self.config.get("transformation_intent", {}).get("weight", 30)
        return min(intent_score, cap)

    def _score_team_size(self, data: dict) -> int:
        hiring = data.get("hiring_count", 0)
        tiers = self.config.get("team_size", {}).get("rules", {}).get("hiring_count", [])
        score = 0
        for tier in sorted(tiers, key=lambda x: x.get("min", 0), reverse=True):
            if hiring >= tier.get("min", 0):
                score = tier.get("score", 0)
                break

        # 招聘数据稀疏时用注册资本推断团队规模下限
        if hiring < 5:
            fb = self.config.get("team_size", {}).get("team_fallback", {})
            if fb.get("enabled"):
                capital = data.get("capital_amount") or 0
                for rule in sorted(fb.get("rules", []), key=lambda x: x.get("capital_threshold", 0), reverse=True):
                    if capital >= rule.get("capital_threshold", 0):
                        score = max(score, rule.get("team_min", 0))
                        break

        return min(score, 15)

    def _score_industry_match(self, data: dict) -> int:
        score = 0
        rules = self.config.get("industry_match", {}).get("rules", {})
        scope = data.get("business_scope", "") or ""
        high_score = rules.get("high_score_per_match", 2)
        low_score = rules.get("low_score_per_match", -1)
        for kw in rules.get("high_match_keywords", []):
            if kw in scope:
                score += high_score
        for kw in rules.get("low_match_keywords", []):
            if kw in scope:
                score += low_score
        return max(0, min(score, 10))

    def batch_score(self, database_url: str, mode="incremental") -> dict:
        """批量评分 — 关联查询各维度数据

        mode='incremental': 仅评分 status='raw' 的企业
        mode='full':        重新评分所有企业（raw + scored）
        """
        conn = psycopg2.connect(database_url)
        stats = {"total": 0, "passed": 0, "failed": 0}
        try:
            with conn.cursor() as cur:
                # 根据模式选择企业
                if mode == "incremental":
                    cur.execute(
                        "SELECT id, company_name, capital_amount, business_scope, "
                        "industry_tags, funding_stage FROM companies WHERE status = %s",
                        ("raw",),
                    )
                else:  # full
                    cur.execute(
                        "SELECT id, company_name, capital_amount, business_scope, "
                        "industry_tags, funding_stage FROM companies WHERE status IN (%s, %s)",
                        ("raw", "scored"),
                    )

                columns = [desc[0] for desc in cur.description]
                companies = [dict(zip(columns, row)) for row in cur.fetchall()]

            stats["total"] = len(companies)

            for company in companies:
                company_id = company["id"]
                name = company.get("company_name", "未知")

                # 1) 查询 tech_profiles
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT ai_job_ratio, cloud_provider, has_github_org, has_tech_blog "
                        "FROM tech_profiles WHERE company_id = %s",
                        (company_id,),
                    )
                    tech_row = cur.fetchone()

                # 2) 查询 recruitments 计数 -> hiring_count
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM recruitments WHERE company_id = %s",
                        (company_id,),
                    )
                    hiring_count = cur.fetchone()[0]

                # 3) 查询 news_mentions 近5条 -> recent_news 文本
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT title, content_summary FROM news_mentions "
                        "WHERE company_id = %s ORDER BY published_at DESC LIMIT 5",
                        (company_id,),
                    )
                    news_rows = cur.fetchall()
                    news_parts = []
                    for title, summary in news_rows:
                        parts = [p for p in (title, summary) if p]
                        if parts:
                            news_parts.append(" ".join(parts))
                    recent_news = " ".join(news_parts)

                # 4) 查询 bidding_records 中 is_digital=TRUE 的计数 -> has_digital_bid
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM bidding_records "
                        "WHERE company_id = %s AND is_digital = TRUE",
                        (company_id,),
                    )
                    digital_bid_count = cur.fetchone()[0]
                    has_digital_bid = digital_bid_count > 0

                # 5) 组装 company_data 字典
                company_data = {
                    "company_id": company_id,
                    "company_name": name,
                    "capital_amount": company.get("capital_amount") or 0,
                    "business_scope": company.get("business_scope") or "",
                    "industry_tags": company.get("industry_tags") or [],
                    "funding_stage": company.get("funding_stage") or "",
                    "ai_job_ratio": tech_row[0] if tech_row else 0,
                    "cloud_provider": tech_row[1] if tech_row else None,
                    "has_github_org": tech_row[2] if tech_row else False,
                    "has_tech_blog": tech_row[3] if tech_row else False,
                    "hiring_count": hiring_count,
                    "recent_news": recent_news,
                    "has_digital_bid": has_digital_bid,
                }

                # 6) 调用评分
                scores = self.score_company(company_data)

                # 7) 写入 ratings 表
                total = scores["total_score"]
                level = self._score_to_level(total)
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO ratings
                            (company_id, total_score, rating_level,
                             tech_score, funding_score, intent_score,
                             team_score, industry_score, rated_by, rated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (company_id, rated_by) DO UPDATE SET
                            total_score = EXCLUDED.total_score,
                            rating_level = EXCLUDED.rating_level,
                            tech_score = EXCLUDED.tech_score,
                            funding_score = EXCLUDED.funding_score,
                            intent_score = EXCLUDED.intent_score,
                            team_score = EXCLUDED.team_score,
                            industry_score = EXCLUDED.industry_score,
                            rated_at = NOW()
                        """,
                        (
                            company_id,
                            total,
                            level,
                            scores["tech_score"],
                            scores["funding_score"],
                            scores["intent_score"],
                            scores["team_score"],
                            scores["industry_score"],
                            "rules_engine",
                        ),
                    )

                # 8) 更新 companies 状态为 scored
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE companies SET status = %s, updated_at = NOW() WHERE id = %s",
                        ("scored", company_id),
                    )

                # 9) 日志记录每家企业评分详情
                logger.info(
                    f"评分: {name} → {total} "
                    f"(tech={scores['tech_score']}, fund={scores['funding_score']}, "
                    f"intent={scores['intent_score']}, team={scores['team_score']}, "
                    f"ind={scores['industry_score']})"
                )

                # 10) 统计通过/未通过
                if total >= self.pass_threshold:
                    stats["passed"] += 1
                else:
                    stats["failed"] += 1

            conn.commit()
            logger.info(
                f"批量评分完成: 总计{stats['total']}家, "
                f"通过{stats['passed']}家, 未通过{stats['failed']}家"
            )
        finally:
            conn.close()
        return stats

    def _score_to_level(self, score: int) -> str:
        """总分 -> 评级等级 S/A/B/C/D（配置化阈值）"""
        t = self.level_thresholds
        if score >= t.get("S", 80):
            return "S"
        elif score >= t.get("A", 60):
            return "A"
        elif score >= t.get("B", 40):
            return "B"
        elif score >= t.get("C", 20):
            return "C"
        else:
            return "D"

    def get_companies_for_llm(self, database_url: str) -> list:
        """获取通过评分阈值的企业列表，供 DeepSeek 深度评级使用

        优先从 ratings 表读取分项分数；若无则实时计算。
        返回 status='scored' 且 total_score >= pass_threshold 的企业。
        """
        conn = psycopg2.connect(database_url)
        results = []
        try:
            with conn.cursor() as cur:
                # JOIN ratings 表获取评分数据
                cur.execute(
                    """
                    SELECT c.id, c.company_name, c.capital_amount,
                           c.business_scope, c.industry_tags,
                           r.total_score, r.tech_score, r.funding_score,
                           r.intent_score, r.team_score, r.industry_score,
                           tp.ai_job_ratio, tp.cloud_provider,
                           tp.has_github_org, tp.has_tech_blog
                    FROM companies c
                    LEFT JOIN ratings r ON r.company_id = c.id AND r.rated_by = 'rules_engine'
                    LEFT JOIN tech_profiles tp ON tp.company_id = c.id
                    WHERE c.status = 'scored'
                    ORDER BY r.total_score DESC NULLS LAST
                    """,
                )
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()

            for row in rows:
                data = dict(zip(columns, row))
                total_score = data.get("total_score")

                # 无 ratings 记录时实时计算
                if total_score is None:
                    # 需要补充 hiring_count / recent_news / has_digital_bid
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT COUNT(*) FROM recruitments WHERE company_id = %s",
                            (data["id"],),
                        )
                        hiring_count = cur.fetchone()[0]

                        cur.execute(
                            "SELECT title, content_summary FROM news_mentions "
                            "WHERE company_id = %s ORDER BY published_at DESC LIMIT 5",
                            (data["id"],),
                        )
                        news_rows = cur.fetchall()
                        news_parts = []
                        for title, summary in news_rows:
                            parts = [p for p in (title, summary) if p]
                            if parts:
                                news_parts.append(" ".join(parts))
                        recent_news = " ".join(news_parts)

                        cur.execute(
                            "SELECT COUNT(*) FROM bidding_records "
                            "WHERE company_id = %s AND is_digital = TRUE",
                            (data["id"],),
                        )
                        has_digital_bid = cur.fetchone()[0] > 0

                    company_data = {
                        "ai_job_ratio": data.get("ai_job_ratio") or 0,
                        "cloud_provider": data.get("cloud_provider"),
                        "has_github_org": data.get("has_github_org") or False,
                        "has_tech_blog": data.get("has_tech_blog") or False,
                        "capital_amount": data.get("capital_amount") or 0,
                        "business_scope": data.get("business_scope") or "",
                        "recent_news": recent_news,
                        "has_digital_bid": has_digital_bid,
                        "hiring_count": hiring_count,
                    }
                    scores = self.score_company(company_data)
                    total_score = scores["total_score"]

                # 仅返回达标企业
                if total_score is not None and total_score >= self.pass_threshold:
                    results.append(data)

        finally:
            conn.close()
        return results


if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv
    import os
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="incremental", choices=["incremental", "full"])
    args = parser.parse_args()
    engine = RatingRulesEngine()
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        stats = engine.batch_score(db_url, mode=args.mode)
        print(f"评分完成: 总计{stats['total']}家, 通过{stats['passed']}家, 未通过{stats['failed']}家")
    else:
        print("请设置 DATABASE_URL 环境变量")
