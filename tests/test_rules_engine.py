"""规则引擎单元测试"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.rules_engine import RatingRulesEngine


class TestRatingRulesEngine:
    """规则引擎5维度评分测试"""

    def setup_method(self):
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "scoring_rules.yaml")
        self.engine = RatingRulesEngine(config_path=config_path)

    def test_high_score_company(self, sample_company):
        """高分企业: 各维度均有得分"""
        result = self.engine.score_company(sample_company)
        assert result["total_score"] >= 60
        assert result["tech_score"] > 0
        assert result["intent_score"] > 0

    def test_low_score_company(self, sample_company_low):
        """低分企业: 总分应低于阈值"""
        result = self.engine.score_company(sample_company_low)
        assert result["total_score"] < 60

    def test_tech_investment_score(self, sample_company):
        """技术投入度评分"""
        score = self.engine._score_tech_investment(sample_company)
        assert 0 <= score <= 30
        assert score > 0  # 有AI岗位+云服务+GitHub+博客

    def test_funding_score(self, sample_company):
        """资金充裕度评分"""
        score = self.engine._score_funding(sample_company)
        assert 0 <= score <= 20

    def test_transformation_intent_score(self, sample_company):
        """转型意向度评分"""
        score = self._score_transformation_intent(sample_company)
        assert 0 <= score <= 25

    def test_team_size_score(self, sample_company):
        """团队规模评分"""
        score = self.engine._score_team_size(sample_company)
        assert 0 <= score <= 15

    def test_industry_match_score(self, sample_company):
        """行业匹配度评分"""
        score = self.engine._score_industry_match(sample_company)
        assert 0 <= score <= 10

    def test_score_range(self, sample_company):
        """总分范围 0-100"""
        result = self.engine.score_company(sample_company)
        assert 0 <= result["total_score"] <= 100

    def test_empty_company(self):
        """空数据企业应得0分"""
        result = self.engine.score_company({})
        assert result["total_score"] == 0
