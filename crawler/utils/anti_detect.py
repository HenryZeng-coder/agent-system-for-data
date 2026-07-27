"""反检测工具 — TLS指纹模拟/请求频率自适应/429自动降速/5xx重试/随机Header"""

import random
import socket
import struct

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from ua_rotator import UARotator


class AntiDetect:
    """自适应请求延迟 + 随机化请求头，降低被反爬识别的概率"""

    # Accept-Language 候选池
    ACCEPT_LANGUAGES = [
        "zh-CN,zh;q=0.9,en;q=0.8",
        "zh-CN,zh;q=0.9",
        "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "en-US,en;q=0.9",
        "en-GB,en;q=0.9,en-US;q=0.8",
        "zh-TW,zh;q=0.9,en-US;q=0.8",
        "ja,en;q=0.9,zh;q=0.8",
    ]

    # Accept-Encoding 候选池
    ACCEPT_ENCODINGS = [
        "gzip, deflate, br",
        "gzip, deflate",
        "gzip, deflate, br;q=1.0, *;q=0.5",
        "br, gzip, deflate",
    ]

    # Accept 候选池
    ACCEPTS = [
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    ]

    def __init__(self, min_delay=0.5, max_delay=30.0, ua_rotator=None):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.current_delay = min_delay
        self.ua_rotator = ua_rotator or UARotator()

        # 5xx 重试计数器
        self._5xx_retry_count = 0
        self._5xx_max_retries = 3
        self._5xx_retry_interval = 5.0

        # 429 指数退避轮次
        self._429_backoff_rounds = 0

    def on_success(self):
        """请求成功，逐步恢复延迟（乘以 0.8 递减）"""
        self.current_delay = max(self.min_delay, self.current_delay * 0.8)
        # 成功后重置 5xx 重试计数
        self._5xx_retry_count = 0
        # 成功后逐步恢复 429 退避轮次
        if self._429_backoff_rounds > 0:
            self._429_backoff_rounds = max(0, self._429_backoff_rounds - 1)

    def on_429(self):
        """429 限速，指数退避：delay 乘以 2^rounds"""
        self._429_backoff_rounds += 1
        backoff_multiplier = 2 ** self._429_backoff_rounds
        self.current_delay = min(self.max_delay, self.min_delay * backoff_multiplier)

    def on_5xx(self):
        """5xx 服务器错误：以 5s 间隔重试，最多 3 次

        Returns:
            bool: True 表示还可以继续重试，False 表示已达到最大重试次数
        """
        self._5xx_retry_count += 1
        if self._5xx_retry_count <= self._5xx_max_retries:
            self.current_delay = self._5xx_retry_interval
            return True
        # 超过最大重试次数，放弃但提高延迟
        self.current_delay = min(self.max_delay, self.current_delay * 2)
        self._5xx_retry_count = 0
        return False

    def get_delay(self):
        """返回当前请求延迟（秒）"""
        return self.current_delay

    def generate_headers(self):
        """生成随机化的请求头字典

        包含：随机 UA、随机 Accept-Language、随机 Accept-Encoding、
        随机 Accept、随机 X-Forwarded-For（伪造 IP）
        """
        headers = {
            "User-Agent": self.ua_rotator.get(),
            "Accept": random.choice(self.ACCEPTS),
            "Accept-Language": random.choice(self.ACCEPT_LANGUAGES),
            "Accept-Encoding": random.choice(self.ACCEPT_ENCODINGS),
            "Connection": "keep-alive",
            "Cache-Control": random.choice(["max-age=0", "no-cache"]),
            "Upgrade-Insecure-Requests": "1",
            "X-Forwarded-For": self._generate_fake_ip(),
            "X-Real-IP": self._generate_fake_ip(),
        }
        return headers

    @staticmethod
    def _generate_fake_ip():
        """生成随机伪造 IP 地址（避开特殊/保留地址段）

        避开的范围：
          - 0.x.x.x       (当前网络)
          - 10.x.x.x       (RFC1918 私有)
          - 100.64–127.x.x (CGN / RFC6598)
          - 127.x.x.x      (环回)
          - 169.254.x.x    (链路本地)
          - 172.16–31.x.x  (RFC1918 私有)
          - 192.0.0.x      (IETF 协议)
          - 192.0.2.x      (TEST-NET-1)
          - 192.88.99.x    (6to4 中继)
          - 192.168.x.x    (RFC1918 私有)
          - 198.18–19.x.x  (基准测试)
          - 224–239.x.x.x  (多播)
          - 240–255.x.x.x  (保留)
        """
        while True:
            ip = socket.inet_ntoa(struct.pack("!I", random.randint(1, 0xFFFFFFFF)))
            first = int(ip.split(".")[0])
            second = int(ip.split(".")[1])
            # Skip reserved/special ranges
            if first in (0, 10, 127):
                continue
            if first >= 224:  # multicast + reserved
                continue
            if first == 100 and 64 <= second <= 127:
                continue
            if first == 169 and second == 254:
                continue
            if first == 172 and 16 <= second <= 31:
                continue
            if first == 192 and second in (0, 2):
                continue
            if first == 192 and second == 88:
                continue
            if first == 192 and second == 168:
                continue
            if first == 198 and 18 <= second <= 19:
                continue
            break
        return ip
