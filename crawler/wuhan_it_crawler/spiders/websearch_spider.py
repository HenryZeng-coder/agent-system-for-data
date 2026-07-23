"""多引擎聚合搜索"""

import scrapy


class WebSearchSpider(scrapy.Spider):
    name = 'websearch'
    allowed_domains = []  # TODO: 填入目标域名
    start_urls = []       # TODO: 填入起始URL

    # 搜索关键词组合
    keywords = ['武汉', '软件开发', '信息技术', '科技', '人工智能', '云计算']

    def start_requests(self):
        """生成初始请求"""
        # TODO: 实现关键词组合生成URL
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse)

    def parse(self, response):
        """列表页解析"""
        # TODO: 提取企业列表和详情页URL
        pass

    def parse_detail(self, response):
        """详情页解析"""
        # TODO: 提取企业详细信息，yield Item
        pass
