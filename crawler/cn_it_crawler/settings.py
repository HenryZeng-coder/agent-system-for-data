"""Scrapy 运行配置"""

import os
import sys

from dotenv import load_dotenv

# 项目根目录 (crawler/cn_it_crawler/settings.py → 上溯两层)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

# settings 是 Scrapy 最先加载的模块, 在此把项目根注入 sys.path,
# spider 才能 `from engine.region import Region` (区域口径与 engine 共用一份实现)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

BOT_NAME = 'cn_it_crawler'
SPIDER_MODULES = ['cn_it_crawler.spiders']
NEWSPIDER_MODULE = 'cn_it_crawler.spiders'

# 并发控制
CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_DELAY = 0.5
DOWNLOAD_TIMEOUT = 30

# 管道注册 (5级)
ITEM_PIPELINES = {
    'cn_it_crawler.pipelines.dedup_pipeline.DedupPipeline': 100,
    'cn_it_crawler.pipelines.filter_pipeline.FilterPipeline': 200,
    'cn_it_crawler.pipelines.clean_pipeline.CleanPipeline': 300,
    'cn_it_crawler.pipelines.validate_pipeline.ValidatePipeline': 400,
    'cn_it_crawler.pipelines.standardize_pipeline.StandardizePipeline': 500,
}

# 中间件注册
DOWNLOADER_MIDDLEWARES = {
    'cn_it_crawler.middlewares.ProxyMiddleware': 100,
    'cn_it_crawler.middlewares.UARotateMiddleware': 200,
    'cn_it_crawler.middlewares.RetryMiddleware': 300,
}

# 断点续传
JOBDIR = 'jobs/default'

# 数据库 (DATABASE_URL 环境变量优先)
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://localhost:5432/rating_system_national')

# ---- 采集范围 (与 config/config.yaml 的 region 段同源) ----
_CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config', 'config.yaml')


def _load_region_config():
    try:
        import yaml

        with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return (yaml.safe_load(f) or {}).get('region') or {}
    except Exception:
        return {}


_REGION = _load_region_config()
REGION_SCOPE = os.getenv('REGION_SCOPE') or _REGION.get('scope', 'national')
REGION_PROVINCE = os.getenv('REGION_PROVINCE') or _REGION.get('province', '')
REGION_CITY = os.getenv('REGION_CITY') or _REGION.get('city', '')
REGION_LOCAL_DOMAINS = _REGION.get('local_domains') or []

# User-Agent
USER_AGENT = 'cn_it_crawler (+https://github.com/E-infoinsight-agent)'

# 遵守 robots.txt
ROBOTSTXT_OBEY = False

# 日志
LOG_LEVEL = 'INFO'
