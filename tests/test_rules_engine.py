"""规则引擎单元测试 — 5维度加权评分 (v2 数据感知自适应评分)

测试覆盖:
- 高分/低分企业
- 各维度满分/0分
- 边界值
- ai_job_ratio >= 修复
- 资本梯度 capital_scale
- D阶段降分
- 经营范围推断 scope_intent
- 跨维度加成 cross_boost
- 团队推断 team_fallback
- 经营范围技术兜底 scope_tech_fallback
- 配置化评级阈值
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
        """技术投入度满分: AI占比>=20% + 云 + GitHub + 博客"""
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
# 3. 资金充裕度 (0-25)
# ================================================================

class TestFunding:
    """资金充裕度维度测试"""

    def test_funding_b_round(self, engine):
        """B轮融资+5000万资本: B(15) + 资本>=1000万(5) + scale>=5000(3) = 23"""
        data = {"funding_stage": "B", "capital_amount": 5000}
        score = engine._score_funding(data)
        assert score == 23, f"B轮+5000万资本应得23分, 实际{score}"

    def test_funding_a_round(self, engine):
        """A轮融资+2000万资本: A(10) + 资本>=1000万(5) = 15"""
        data = {"funding_stage": "A", "capital_amount": 2000}
        score = engine._score_funding(data)
        assert score == 15, f"A轮+2000万资本应得15分, 实际{score}"

    def test_funding_none(self, engine):
        """无融资+小资本: 0分"""
        data = {"funding_stage": "", "capital_amount": 100}
        score = engine._score_funding(data)
        assert score == 0, f"无融资+100万应得0分, 实际{score}"

    def test_funding_capital_only(self, engine):
        """仅有注册资本达标: 5分"""
        data = {"funding_stage": "", "capital_amount": 2000}
        score = engine._score_funding(data)
        assert score == 5, f"仅2000万资本应得5分, 实际{score}"


# ================================================================
# 4. 转型意向度 (0-30)
# ================================================================

class TestTransformationIntent:
    """转型意向度维度测试"""

    def test_intent_high(self, engine):
        """高转型意向: 4个新闻关键词(20分) + 数字化招投标(10分) = 30"""
        data = {
            "recent_news": "完成数字化转型，引入AI和云计算技术",
            "has_digital_bid": True,
        }
        score = engine._score_transformation_intent(data)
        assert score == 30, f"高转型意向应得30分, 实际{score}"

    def test_intent_none(self, engine):
        """无转型意向: 0分"""
        data = {"recent_news": "日常经营", "has_digital_bid": False}
        score = engine._score_transformation_intent(data)
        assert score == 0, f"无转型意向应得0分, 实际{score}"

    def test_intent_news_only(self, engine):
        """仅有新闻关键词匹配"""
        data = {"recent_news": "推进数字化转型和AI应用", "has_digital_bid": False}
        score = engine._score_transformation_intent(data)
        assert 0 < score < 30, f"仅有新闻匹配应得0-30分, 实际{score}"

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

    def test_industry_expanded_keywords(self, engine):
        """扩展行业关键词: 网络安全+机器人+物联网 = 3*2=6"""
        data = {"business_scope": "网络安全、机器人、物联网"}
        score = engine._score_industry_match(data)
        assert score == 6, f"3个扩展高匹配词应得6分, 实际{score}"


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
        """恰好60分边界: A级入口"""
        data = {
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
        result = engine.score_company(data)
        # tech: 15(AI)+5(cloud)=20  scope_fallback: "传统行业"无匹配→0
        # funding: 10(A)+5(capital)=15
        # intent_base: 3 keywords*5=15, scope_intent:无→0, cross_boost: tech=20<25→0
        # team: 20人→10
        # industry: 0
        # total: 20+15+15+10+0 = 60
        assert result["total_score"] == 60, f"边界60分测试: 实际{result['total_score']}"

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
                        "intent_score", "team_score", "industry_score",
                        "data_completeness"}
        assert set(result.keys()) == expected_keys


# ================================================================
# 8. ai_job_ratio 边界修复 (> → >=)
# ================================================================

class TestAiJobRatioBoundary:
    """ai_job_ratio 恰好在阈值应得分（>= 修复）"""

    def test_ai_ratio_exactly_at_threshold(self, engine):
        """ai_job_ratio=0.2 应给15分"""
        data = {"ai_job_ratio": 0.2}
        score = engine._score_tech_investment(data)
        assert score >= 15, f"ai_job_ratio=0.2 with >=应得>=15, 实际{score}"

    def test_ai_ratio_just_below_threshold(self, engine):
        """ai_job_ratio=0.19 不应给AI分"""
        data = {"ai_job_ratio": 0.19}
        score = engine._score_tech_investment(data)
        assert score < 15, f"ai_job_ratio=0.19 不应得AI分, 实际{score}"


# ================================================================
# 9. 资本梯度 capital_scale
# ================================================================

class TestCapitalScale:
    """注册资本梯度加分"""

    def test_capital_huge(self, engine):
        """capital >= 50000万(5亿) → B(15)+capital≥1000(5)+scale≥50000(8)=28, cap 25"""
        data = {"funding_stage": "B", "capital_amount": 128921}
        score = engine._score_funding(data)
        assert score == 25, f"大资本应cap在25, 实际{score}"

    def test_capital_large(self, engine):
        """capital >= 10000万(1亿) → B(15)+capital≥1000(5)+scale≥10000(5)=25"""
        data = {"funding_stage": "B", "capital_amount": 15000}
        score = engine._score_funding(data)
        assert score == 25, f"1亿资本+cap 25, 实际{score}"

    def test_capital_medium(self, engine):
        """capital >= 5000万 → A(10)+capital≥1000(5)+scale≥5000(3)=18"""
        data = {"funding_stage": "A", "capital_amount": 7050}
        score = engine._score_funding(data)
        assert score == 18, f"5000万级应得18, 实际{score}"

    def test_capital_small(self, engine):
        """capital < 5000万 不获梯度分 → A(10)+capital≥1000(5)=15"""
        data = {"funding_stage": "A", "capital_amount": 2000}
        score = engine._score_funding(data)
        assert score == 15, f"小资本无梯度, 应得15, 实际{score}"


# ================================================================
# 10. D阶段降分
# ================================================================

class TestFundingStageD:
    """D阶段应低于A阶段"""

    def test_d_stage_lower_than_a(self, engine):
        data_d = {"funding_stage": "D", "capital_amount": 2000}
        data_a = {"funding_stage": "A", "capital_amount": 2000}
        score_d = engine._score_funding(data_d)
        score_a = engine._score_funding(data_a)
        assert score_d < score_a, f"D阶段({score_d})应<A阶段({score_a})"

    def test_d_stage_score(self, engine):
        """D(5) + capital<1000(0) = 5"""
        data = {"funding_stage": "D", "capital_amount": 500}
        score = engine._score_funding(data)
        assert score == 5, f"D阶段+小资本应得5, 实际{score}"


# ================================================================
# 11. 经营范围推断转型意向 scope_intent
# ================================================================

class TestScopeIntent:
    """经营范围推断转型意向"""

    def test_ai_in_scope(self, engine):
        """business_scope含"人工智能"→+5"""
        data = {"business_scope": "人工智能应用开发", "recent_news": "", "has_digital_bid": False}
        score = engine._score_transformation_intent(data)
        assert score >= 5, f"AI in scope应得>=5, 实际{score}"

    def test_digital_transform_in_scope(self, engine):
        """business_scope含"数字化转型"→+5"""
        data = {"business_scope": "数字化转型服务", "recent_news": "", "has_digital_bid": False}
        score = engine._score_transformation_intent(data)
        assert score >= 5, f"数字化转型 in scope应得>=5, 实际{score}"

    def test_cloud_bigdata_in_scope(self, engine):
        """business_scope含"云计算"或"大数据"→同一规则组+3"""
        data = {"business_scope": "云计算、大数据分析", "recent_news": "", "has_digital_bid": False}
        score = engine._score_transformation_intent(data)
        assert score >= 3, f"云计算/大数据 in scope应得>=3, 实际{score}"

    def test_no_intent_signal(self, engine):
        """business_scope无转型信号→0"""
        data = {"business_scope": "办公设备销售", "recent_news": "", "has_digital_bid": False}
        score = engine._score_transformation_intent(data)
        assert score == 0, f"无信号应得0, 实际{score}"


# ================================================================
# 12. 跨维度加成 cross_boost
# ================================================================

class TestCrossBoost:
    """跨维度转型意向加成"""

    def test_tech_boost(self, engine):
        """技术投入>=25 → intent+5"""
        data = {
            "ai_job_ratio": 0.35, "cloud_provider": "AWS",
            "has_github_org": True, "has_tech_blog": True,
            "recent_news": "", "has_digital_bid": False,
            "business_scope": "传统服务", "capital_amount": 100,
            "funding_stage": "", "hiring_count": 0,
        }
        result = engine.score_company(data)
        # tech=30≥25, 所以intent应有+5加成(即使base=0)
        assert result["intent_score"] >= 5, f"tech≥25应给intent加成, 实际intent={result['intent_score']}"

    def test_capital_tech_boost(self, engine):
        """大型成熟技术企业(capital≥5000 + tech≥10) → intent+5"""
        data = {
            "ai_job_ratio": 0.25, "cloud_provider": "华为云",
            "has_github_org": False, "has_tech_blog": False,
            "capital_amount": 75000, "funding_stage": "B",
            "recent_news": "", "has_digital_bid": False,
            "business_scope": "光纤通信和信息技术开发",
            "hiring_count": 0,
        }
        result = engine.score_company(data)
        # tech=15+5=20≥10, capital=75000≥5000 → +5
        assert result["intent_score"] >= 5, f"大资本+技术应给intent加成, 实际intent={result['intent_score']}"


# ================================================================
# 13. 团队推断 team_fallback
# ================================================================

class TestTeamFallback:
    """注册资本推断团队规模"""

    def test_large_company_no_hiring(self, engine):
        """capital>=50000万+0招聘 → 推断team=10"""
        data = {"hiring_count": 0, "capital_amount": 128921}
        score = engine._score_team_size(data)
        assert score >= 10, f"大公司无招聘应推断team>=10, 实际{score}"

    def test_medium_company_no_hiring(self, engine):
        """capital>=5000万+0招聘 → 推断team=5"""
        data = {"hiring_count": 0, "capital_amount": 7050}
        score = engine._score_team_size(data)
        assert score >= 5, f"中公司无招聘应推断team>=5, 实际{score}"

    def test_small_company_no_hiring(self, engine):
        """capital<5000万+0招聘 → 不推断"""
        data = {"hiring_count": 0, "capital_amount": 500}
        score = engine._score_team_size(data)
        assert score == 0, f"小公司无招聘不应推断, 实际{score}"

    def test_hiring_takes_priority(self, engine):
        """有实际招聘数据时应优先"""
        data = {"hiring_count": 60, "capital_amount": 128921}
        score = engine._score_team_size(data)
        assert score == 15, f"有招聘数据应优先, 实际{score}"


# ================================================================
# 14. 经营范围技术兜底 scope_tech_fallback
# ================================================================

class TestScopeTechFallback:
    """经营范围推断技术投入下限"""

    def test_ai_in_scope_fallback(self, engine):
        """无技术数据+scope含"人工智能"→tech_min=10"""
        data = {"ai_job_ratio": 0, "business_scope": "人工智能应用开发"}
        score = engine._score_tech_investment(data)
        assert score >= 10, f"AI in scope应推断tech>=10, 实际{score}"

    def test_software_in_scope_fallback(self, engine):
        """无技术数据+scope含"软件开发"→tech_min=8"""
        data = {"ai_job_ratio": 0, "business_scope": "软件开发与销售"}
        score = engine._score_tech_investment(data)
        assert score >= 8, f"软件开发 in scope应推断tech>=8, 实际{score}"

    def test_data_driven_takes_priority(self, engine):
        """数据驱动分更高时不被兜底降低"""
        data = {
            "ai_job_ratio": 0.35, "cloud_provider": "AWS",
            "has_github_org": True, "has_tech_blog": True,
            "business_scope": "人工智能应用开发",
        }
        score = engine._score_tech_investment(data)
        assert score == 30, f"数据驱动分更高时不应被降低, 实际{score}"

    def test_no_tech_signal(self, engine):
        """scope无技术信号→不兜底"""
        data = {"ai_job_ratio": 0, "business_scope": "办公设备销售"}
        score = engine._score_tech_investment(data)
        assert score == 0, f"无信号不应兜底, 实际{score}"


# ================================================================
# 15. 配置化评级阈值
# ================================================================

class TestLevelThresholds:
    """评级阈值测试 (S≥80, A≥60, B≥40, C≥20, D<20)"""

    def test_s_level(self, engine):
        assert engine._score_to_level(80) == "S"
        assert engine._score_to_level(79) == "A"

    def test_a_level(self, engine):
        assert engine._score_to_level(60) == "A"
        assert engine._score_to_level(59) == "B"

    def test_b_level(self, engine):
        assert engine._score_to_level(40) == "B"
        assert engine._score_to_level(39) == "C"

    def test_c_level(self, engine):
        assert engine._score_to_level(20) == "C"
        assert engine._score_to_level(19) == "D"

    def test_d_level(self, engine):
        assert engine._score_to_level(0) == "D"

    def test_thresholds_from_config(self, engine):
        """阈值应从配置读取"""
        assert engine.level_thresholds["S"] == 80
        assert engine.level_thresholds["A"] == 60
        assert engine.level_thresholds["B"] == 40
        assert engine.level_thresholds["C"] == 20
