import os
import pytest

@pytest.fixture(scope="session")
def database_url():
    return os.getenv("DATABASE_URL", "postgresql://kc@localhost:5432/rating_system")

@pytest.fixture
def sample_company():
    return {"company_name":"test","credit_code":"91420100MA4KTEST01","business_scope":"AI",   "capital_amount":5000,"ai_job_ratio":0.35,"cloud_provider":"AWS","has_github_org":True,"has_tech_blog":True,"funding_stage":"A","hiring_count":30,"recent_news":"AI融资","has_digital_bid":True}

@pytest.fixture
def sample_company_low():
    return {"company_name":"low","credit_code":"91420100MA4KTEST02","business_scope":"硬件",   "capital_amount":100,"ai_job_ratio":0,"cloud_provider":None,"has_github_org":False,"has_tech_blog":False,"funding_stage":"","hiring_count":2,"recent_news":"","has_digital_bid":False}
