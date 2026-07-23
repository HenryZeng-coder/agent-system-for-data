"""反检测工具"""


class AntiDetect:
    """TLS指纹模拟/请求频率自适应/429自动降速"""

    def __init__(self, min_delay=0.5, max_delay=5.0):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.current_delay = min_delay

    def on_success(self):
        """请求成功，逐步恢复延迟"""
        self.current_delay = max(self.min_delay, self.current_delay * 0.8)

    def on_429(self):
        """429限速，指数退避"""
        self.current_delay = min(self.max_delay, self.current_delay * 2)

    def get_delay(self):
        return self.current_delay
