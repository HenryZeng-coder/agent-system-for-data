"""规则引擎单元测试 — 5维度加权评分

15个测试用例覆盖:
- 高分/低分企业
- 各维度满分/0分
- 边界值
- 总分范围
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from engine.rules_engine import RatingRulesEngine


@pytest.fixture
def engine():
    """创建引擎实例"""
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "scoring_rules.yaml")
    return RatingRulesEngine(config_path=config_path)


@pytest.fixture
def high_score_data():
    """高分企业数据: AI占比高+云+GitHub+博客+B轮融资+数字化招投标+大团队+高匹配"""
    return {
        "ai_job_ratio": 0.35,
        "cloud_provider": "AWS",
        "has_github_org": True,
        "has_tech_blog": True,
        "funding_stage": "B",
        "capital_amount": 5000,
        "recent_news": "完成B轮融资，将加大AI和数字化转型投入",
        "has_digital_bid": True,
        "hiring_count": 60,
        "business_scope": "人工智能软件开发、云计算、大数据分析、系统集成",
    }


@pytest.fixture
def low_score_data():
    """低分企业数据: 无AI+无云+无GitHub+无融资+小团队+低匹配"""
    return {
        "ai_job_ratio": 0,
        "cloud_provider": None,
        "has_github_org": False,
        "has_tech_blog": False,
        "funding_stage": "",
        "capital_amount": 100,
        "recent_news": "",
        "has_digital_bid": False,
        "hiring_count": 2,
        "business_scope": "办公设备销售、维修",
    }


# ================================================================
# 1. 高分/低分企业
# ================================================================

class TestHighLowScore:
    """总分级别测试"""

    def test_high_score_company(self, engine, high_score_data):
        """高分企业: 总分 >= 60"""
        result = engine.score_company(high_score_data)
        assert result["total_score"] >= 60, f"高分企业得分 {result['total_score']} < 60"

    def test_low_score_company(self, engine, low_score_data):
        """低分企业: 总分 < 60"""
        result = engine.score_company(low_score_data)
        assert result["total_score"] < 60, f"低分企业得分 {result['total_score']} >= 60"


# ================================================================
# 2. 技术投入度 (0-30)
# ================================================================

class TestTechInvestment:
    """技术投入度维度测试"""

    def test_tech_investment_all(self, engine):
        """技术投入度满分: AI占比>20% + 云 + GitHub + 博客"""
        data = {
            "ai_job_ratio": 0.35,
            "cloud_provider": "阿里云",
            "has_github_org": True,
            "has_tech_blog": True,
        }
        score = engine._score_tech_investment(data)
        assert score == 30, f"技术投入度应为30, 实际{score}"

    def test_tech_investment_none(self, engine):
        """技术投入度0分: 无任何技术投入指标"""
        data = {
            "ai_job_ratio": 0,
            "cloud_provider": None,
            "has_github_org": False,
            "has_tech_blog": False,
        }
        score = engine._score_tech_investment(data)
        assert score == 0, f"无技术投入应得0分, 实际{score}"

    def test_tech_investment_partial(self, engine):
        """技术投入度部分得分: 仅有AI岗位占比"""
        data = {
            "ai_job_ratio": 0.25,
            "cloud_provider": None,
            "has_github_org": False,
            "has_tech_blog": False,
        }
        score = engine._score_tech_investment(data)
        assert 0 < score < 30, f"部分技术投入应得0-30分, 实际{score}"

    def test_tech_investment_below_threshold(self, engine):
        """AI岗位占比低于阈值: 不给AI分"""
        data = {
            "ai_job_ratio": 0.1,  # 低于 0.2 阈值
            "cloud_provider": None,
            "has_github_org": False,
            "has_tech_blog": False,
        }
        score = engine._score_tech_investment(data)
        assert score == 0, f"AI占比低于阈值应得0分, 实际{score}"


# ================================================================
# 3. 资金充裕度 (0-20)
# ================================================================

class TestFunding:
    """资金充裕度维度测试"""

    def test_funding_b_round(self, engine):
        """B轮融资: 15分 + 注册资本>=1000万5分 = 20"""
        data = {"funding_stage": "B", "capital_amount": 5000}
        score = engine._score_funding(data)
        assert score == 20, f"B轮+5000万资本应得20分, 实际{score}"

    def test_funding_a_round(self, engine):
        """A轮融资: 10分 + 注册资本>=1000万5分 = 15"""
        data = {"funding_stage": "A", "capital_amount": 2000}
        score = engine._score_funding(data)
        assert score == 15, f"A轮+2000万资本应得15分, 实际{score}"

    def test_funding_none(self, engine):
        """无融资: 0分"""
        data = {"funding_stage": "", "capital_amount": 100}
        score = engine._score_funding(data)
        assert score == 0, f"无融资+100万应得0分, 实际{score}"

    def test_funding_capital_only(self, engine):
        """仅有注册资本达标"""
        data = {"funding_stage": "", "capital_amount": 2000}
        score = engine._score_funding(data)
        assert score == 5, f"仅2000万资本应得5分, 实际{score}"


# ================================================================
# 4. 转型意向度 (0-25)
# ================================================================

class TestTransformationIntent:
    """转型意向度维度测试"""

    def test_intent_high(self, engine):
        """高转型意向: 新闻含3个关键词(15分) + 数字化招投标(10分) = 25"""
        data = {
            "recent_news": "完成数字化转型，引入AI和云计算技术",
            "has_digital_bid": True,
        }
        score = engine._score_transformation_intent(data)
        assert score == 25, f"高转型意向应得25分, 实际{score}"

    def test_intent_none(self, engine):
        """无转型意向: 0分"""
        data = {"recent_news": "日常经营", "has_digital_bid": False}
        score = engine._score_transformation_intent(data)
        assert score == 0, f"无转型意向应得0分, 实际{score}"

    def test_intent_news_only(self, engine):
        """仅有新闻关键词匹配"""
        data = {"recent_news": "推进数字化转型和AI应用", "has_digital_bid": False}
        score = engine._score_transformation_intent(data)
        assert 0 < score < 25, f"仅有新闻匹配应得0-25分, 实际{score}"

    def test_intent_bid_only(self, engine):
        """仅有数字化招投标"""
        data = {"recent_news": "", "has_digital_bid": True}
        score = engine._score_transformation_intent(data)
        assert score == 10, f"仅数字化招投标应得10分, 实际{score}"


# ================================================================
# 5. 团队规模 (0-15)
# ================================================================

class TestTeamSize:
    """团队规模维度测试"""

    def test_team_large(self, engine):
        """大团队 >50人: 15分"""
        data = {"hiring_count": 60}
        score = engine._score_team_size(data)
        assert score == 15, f"60人招聘应得15分, 实际{score}"

    def test_team_medium(self, engine):
        """中等团队 20-50人: 10分"""
        data = {"hiring_count": 30}
        score = engine._score_team_size(data)
        assert score == 10, f"30人招聘应得10分, 实际{score}"

    def test_team_small(self, engine):
        """小团队 5-20人: 5分"""
        data = {"hiring_count": 10}
        score = engine._score_team_size(data)
        assert score == 5, f"10人招聘应得5分, 实际{score}"

    def test_team_tiny(self, engine):
        """微型团队 <5人: 0分"""
        data = {"hiring_count": 2}
        score = engine._score_team_size(data)
        assert score == 0, f"2人招聘应得0分, 实际{score}"


# ================================================================
# 6. 行业匹配度 (0-10)
# ================================================================

class TestIndustryMatch:
    """行业匹配度维度测试"""

    def test_industry_high(self, engine):
        """高行业匹配: 云计算+AI+大数据+系统集成+软件开发 = 5*2=10"""
        data = {"business_scope": "云计算、人工智能、大数据、系统集成、软件开发"}
        score = engine._score_industry_match(data)
        assert score == 10, f"5个高匹配词应得10分, 实际{score}"

    def test_industry_low(self, engine):
        """低行业匹配: 运维+硬件 = 2*(-1)=-2 → clamped to 0"""
        data = {"business_scope": "运维服务、硬件销售"}
        score = engine._score_industry_match(data)
        assert score == 0, f"低匹配词应得0分(下限), 实际{score}"

    def test_industry_mixed(self, engine):
        """混合匹配: AI(高+2) + 运维(低-1) = 1"""
        data = {"business_scope": "人工智能开发、运维服务"}
        score = engine._score_industry_match(data)
        assert score == 1, f"高+低混合应得1分, 实际{score}"


# ================================================================
# 7. 边界值与总体
# ================================================================

class TestBoundaryAndOverall:
    """边界值和总体测试"""

    def test_total_range(self, engine, high_score_data):
        """总分在0-100范围内"""
        result = engine.score_company(high_score_data)
        assert 0 <= result["total_score"] <= 100

    def test_empty_data(self, engine):
        """空数据: 所有维度0分"""
        result = engine.score_company({})
        assert result["total_score"] == 0
        assert result["tech_score"] == 0
        assert result["funding_score"] == 0
        assert result["intent_score"] == 0
        assert result["team_score"] == 0
        assert result["industry_score"] == 0

    def test_boundary_60(self, engine):
        """恰好60分边界: 人工构造使总分=60"""
        # tech: AI(15) + cloud(5) = 20
        # funding: A轮(10) + 资本>=1000万(5) = 15
        # intent: 1个关键词(5) + digital_bid(10) = 15
        # team: 5-20人(5)
        # industry: 云计算(2) + 软件开发(2) = 4 → min(4+0, 10) = 4
        # total: 20 + 15 + 15 + 5 + 4 → wait, let me compute exactly
        # Actually: let me just compute and verify >= 60
        data = {
            "ai_job_ratio": 0.25,
            "cloud_provider": "华为云",
            "has_github_org": False,
            "has_tech_blog": False,
            "funding_stage": "A",
            "capital_amount": 2000,
            "recent_news": "推进数字化转型",
            "has_digital_bid": True,
            "hiring_count": 25,
            "business_scope": "传统行业服务",
        }
        result = engine.score_company(data)
        # "推进数字化转型" contains "数字" and "转型" → 2*5=10
        # intent: 10 + digital_bid(10) = 20 (cap 25)
        # So total = 20(tech) + 15(funding) + 20(intent) + 10(team) + 0(industry) = 65
        # Adjust to exactly 60: remove digital_bid and have 3 keyword matches (15)
        data2 = {
            "ai_job_ratio": 0.25,
            "cloud_provider": "华为云",
            "has_github_org": False,
            "has_tech_blog": False,
            "funding_stage": "A",
            "capital_amount": 2000,
            "recent_news": "数字转型智能",
            "has_digital_bid": False,
            "hiring_count": 20,
            "business_scope": "传统行业",
        }
        result2 = engine.score_company(data2)
        # tech: 15(AI)+5(cloud) = 20
        # funding: 10(A)+5(capital) = 15
        # intent: 3 keywords * 5 = 15 (cap 15)
        # team: 20-50 → 10
        # industry: 0
        # total: 20+15+15+10+0 = 60
        assert result2["total_score"] == 60, f"边界60分测试: 实际{result2['total_score']}"

    def test_all_max(self, engine):
        """各维度满分: 总分应不超过100"""
        data = {
            "ai_job_ratio": 0.5,
            "cloud_provider": "阿里云",
            "has_github_org": True,
            "has_tech_blog": True,
            "funding_stage": "B",
            "capital_amount": 10000,
            "recent_news": "数字化转型 AI 智能云 大模型 中台",
            "has_digital_bid": True,
            "hiring_count": 100,
            "business_scope": "云计算、人工智能、大数据、系统集成、软件开发",
        }
        result = engine.score_company(data)
        assert result["total_score"] == 100, f"满分应被cap到100, 实际{result['total_score']}"

    def test_score_keys(self, engine, high_score_data):
        """返回结果包含所有分项键"""
        result = engine.score_company(high_score_data)
        expected_keys = {"total_score", "tech_score", "funding_score",
                        "intent_score", "team_score", "industry_score"}
        assert set(result.keys()) == expected_keys
