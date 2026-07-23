"""代理IP池管理"""


class ProxyPool:
    """代理IP池: 获取/验证/剔除/自动切换"""

    def __init__(self, api_url=None):
        self.api_url = api_url
        self.proxies = []
        self.failed = {}

    def get_proxy(self):
        """获取一个可用代理"""
        # TODO: 实现
        return None

    def mark_failed(self, proxy):
        """标记代理失败，连续失败3次剔除"""
        # TODO: 实现
        pass

    def refresh(self):
        """刷新代理池"""
        # TODO: 实现
        pass
