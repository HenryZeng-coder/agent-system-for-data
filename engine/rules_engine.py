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
        self.pass_threshold = 60

    def score_company(self, company_data: dict) -> dict:
        tech = self._score_tech_investment(company_data)
        funding = self._score_funding(company_data)
        intent = self._score_transformation_intent(company_data)
        team = self._score_team_size(company_data)
        industry = self._score_industry_match(company_data)
        total = min(tech + funding + intent + team + industry, 100)
        return {
            "total_score": total,
            "tech_score": tech,
            "funding_score": funding,
            "intent_score": intent,
            "team_score": team,
            "industry_score": industry,
        }

    def _score_tech_investment(self, data: dict) -> int:
        score = 0
        rules = self.config.get("tech_investment", {}).get("rules", {})
        ai_rule = rules.get("ai_job_ratio", {})
        if data.get("ai_job_ratio", 0) > ai_rule.get("threshold", 0.2):
            score += ai_rule.get("score", 15)
        if data.get("cloud_provider"):
            score += rules.get("cloud_provider", {}).get("score", 5)
        if data.get("has_github_org"):
            score += rules.get("github_org", {}).get("score", 5)
        if data.get("has_tech_blog"):
            score += rules.get("tech_blog", {}).get("score", 5)
        return min(score, 30)

    def _score_funding(self, data: dict) -> int:
        score = 0
        rules = self.config.get("funding", {}).get("rules", {})
        stage = data.get("funding_stage", "")
        stage_scores = rules.get("funding_stage", {})
        if stage in stage_scores:
            score += stage_scores[stage]
        capital_rule = rules.get("registered_capital", {})
        if data.get("capital_amount", 0) >= capital_rule.get("threshold", 1000):
            score += capital_rule.get("score", 5)
        return min(score, 20)

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
        return min(score, 25)

    def _score_team_size(self, data: dict) -> int:
        hiring = data.get("hiring_count", 0)
        tiers = self.config.get("team_size", {}).get("rules", {}).get("hiring_count", [])
        for tier in sorted(tiers, key=lambda x: x.get("min", 0), reverse=True):
            if hiring >= tier.get("min", 0):
                return tier.get("score", 0)
        return 0

    def _score_industry_match(self, data: dict) -> int:
        score = 0
        rules = self.config.get("industry_match", {}).get("rules", {})
        scope = data.get("business_scope", "") or ""
        for kw in rules.get("high_match_keywords", []):
            if kw in scope:
                score += rules.get("score_per_match", 2)
        for kw in rules.get("low_match_keywords", []):
            if kw in scope:
                score += rules.get("score_per_match", -1)
        return max(0, min(score, 10))

    def batch_score(self, database_url: str, mode="incremental") -> dict:
        conn = psycopg2.connect(database_url)
        stats = {"total": 0, "passed": 0, "failed": 0}
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM companies WHERE status = %s", ("raw",))
                columns = [desc[0] for desc in cur.description]
                companies = [dict(zip(columns, row)) for row in cur.fetchall()]
            stats["total"] = len(companies)
            for company in companies:
                scores = self.score_company(company)
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE companies SET status = %s, updated_at = NOW() WHERE id = %s",
                        ("scored", company["id"]),
                    )
                if scores["total_score"] >= self.pass_threshold:
                    stats["passed"] += 1
                else:
                    stats["failed"] += 1
            conn.commit()
        finally:
            conn.close()
        return stats

    def get_companies_for_glm(self, database_url: str) -> list:
        return []


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
