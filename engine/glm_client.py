"""GLM-5.1 API 客户端 — 批量评级 + 多层容错"""

import json
import time
import logging
import requests
from typing import List, Dict

logger = logging.getLogger(__name__)


class GLMRatingClient:
    """GLM-5.1 批量评级客户端"""

    def __init__(self, api_key: str, prompt_template_path: str = "engine/prompts/analysis_prompt.md",
                 base_url: str = "https://open.bigmodel.cn/api/paas/v4",
                 model: str = "GLM-5.1", temperature: float = 0.1,
                 max_tokens: int = 500, timeout: int = 30,
                 batch_size: int = 5, rate_limit: float = 0.5):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.batch_size = batch_size
        self.rate_limit = rate_limit
        with open(prompt_template_path, "r", encoding="utf-8") as f:
            self.prompt_template = f.read()
        self.few_shot_examples = []
        try:
            few_shot_path = prompt_template_path.replace("analysis_prompt.md", "few_shot_examples.json")
            with open(few_shot_path, "r", encoding="utf-8") as f:
                self.few_shot_examples = json.load(f)
        except FileNotFoundError:
            pass

    def batch_rate(self, companies: List[Dict]) -> List[Dict]:
        results = []
        for i in range(0, len(companies), self.batch_size):
            batch = companies[i:i + self.batch_size]
            prompt = self._build_batch_prompt(batch)
            response_text = self._call_glm(prompt)
            if response_text:
                parsed = self._parse_response(response_text, batch)
                results.extend(parsed)
            time.sleep(self.rate_limit)
        return results

    def _build_batch_prompt(self, batch: List[Dict]) -> str:
        sections = []
        for i, company in enumerate(batch):
            section = f"""[企业{i+1}]
名称：{company.get("company_name", "未知")}
经营范围：{company.get("business_scope", "未知")}
技术岗位占比：{company.get("ai_job_ratio", 0) * 100 if company.get("ai_job_ratio") else "未知"}%
融资阶段：{company.get("funding_stage", "未知")}
近期动态：{company.get("recent_news", "无")}
"""
            sections.append(section)
        return self.prompt_template.replace("{companies}", "\n".join(sections))

    def _call_glm(self, prompt: str, retries_5xx: int = 3) -> str:
        wait_time = 1
        while True:
            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": self.temperature,
                        "max_tokens": self.max_tokens,
                    },
                    timeout=self.timeout,
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
                elif resp.status_code == 429:
                    logger.warning(f"429限速, 等待{wait_time}秒")
                    time.sleep(wait_time)
                    wait_time = min(wait_time * 2, 60)
                elif resp.status_code >= 500:
                    retries_5xx -= 1
                    if retries_5xx <= 0:
                        logger.error("5xx连续3次失败")
                        return None
                    time.sleep(5)
                else:
                    logger.error(f"API异常: {resp.status_code}")
                    return None
            except requests.Timeout:
                logger.error("API超时")
                return None
            except Exception as e:
                logger.error(f"API调用异常: {e}")
                return None

    def _parse_response(self, response: str, batch: List[Dict]) -> List[Dict]:
        try:
            data = json.loads(response)
            results = data if isinstance(data, list) else [data]
            return [r for r in results if self._validate_result(r)]
        except json.JSONDecodeError:
            logger.warning("JSON解析失败")
            return []

    def _validate_result(self, result: dict) -> bool:
        try:
            score = result.get("score")
            level = result.get("level")
            tags = result.get("demand_tags")
            if not isinstance(score, int) or not (0 <= score <= 100):
                return False
            if level not in ("S", "A", "B", "C", "D"):
                return False
            if not isinstance(tags, list) or len(tags) == 0:
                return False
            return True
        except Exception:
            return False

    def update_database(self, results: List[Dict], database_url: str):
        # TODO: 实现数据库写入 ratings + 更新 companies.status='rated'
        pass


if __name__ == "__main__":
    from dotenv import load_dotenv
    import os
    load_dotenv()
    client = GLMRatingClient(api_key=os.getenv("GLM_API_KEY", ""))
    print("GLM客户端就绪")
