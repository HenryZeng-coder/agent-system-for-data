"""Scrapy 运行配置"""

import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env'))

BOT_NAME = 'wuhan_it_crawler'
SPIDER_MODULES = ['wuhan_it_crawler.spiders']
NEWSPIDER_MODULE = 'wuhan_it_crawler.spiders'

# 并发控制
CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_DELAY = 0.5
DOWNLOAD_TIMEOUT = 30

# 管道注册 (5级)
ITEM_PIPELINES = {
    'wuhan_it_crawler.pipelines.dedup_pipeline.DedupPipeline': 100,
    'wuhan_it_crawler.pipelines.filter_pipeline.FilterPipeline': 200,
    'wuhan_it_crawler.pipelines.clean_pipeline.CleanPipeline': 300,
    'wuhan_it_crawler.pipelines.validate_pipeline.ValidatePipeline': 400,
    'wuhan_it_crawler.pipelines.standardize_pipeline.StandardizePipeline': 500,
}

# 中间件注册
DOWNLOADER_MIDDLEWARES = {
    'wuhan_it_crawler.middlewares.ProxyMiddleware': 100,
    'wuhan_it_crawler.middlewares.UARotateMiddleware': 200,
    'wuhan_it_crawler.middlewares.RetryMiddleware': 300,
}

# 断点续传
JOBDIR = 'jobs/default'

# 数据库
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://kc@localhost:5432/rating_system')

# User-Agent
USER_AGENT = 'wuhan_it_crawler (+https://github.com/E-infoinsight-agent)'

# 遵守 robots.txt
ROBOTSTXT_OBEY = False

# 日志
LOG_LEVEL = 'INFO'
