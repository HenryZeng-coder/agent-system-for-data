"""Scrapy 下载中间件"""

import random


class ProxyMiddleware:
    """代理IP中间件 — 从 proxy_pool 获取代理"""

    def __init__(self):
        self.proxy_pool = None  # TODO: 初始化 ProxyPool

    def process_request(self, request, spider):
        # TODO: 从代理池获取代理
        pass


class UARotateMiddleware:
    """User-Agent 随机轮换中间件"""

    USER_AGENTS = [
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    ]

    def process_request(self, request, spider):
        request.headers['User-Agent'] = random.choice(self.USER_AGENTS)
