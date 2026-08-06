"""DeepSeek API 客户端 — 批量评级 + 多层容错 + TPM自适应限流 + 断点续跑

核心增强:
1. 429 TPM 限流: 指数退避 + 最大等待120秒 + TPM自适应降速
2. 断点续跑: 记录已评级 company_id，中断后自动跳过已完成企业
3. 自动恢复: batch_rate 遇到429后等待重试，不丢弃未完成批次
4. 进度持久化: 每个batch成功后写入进度文件
"""

import json
import time
import logging
import os
import requests
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class LLMRatingClient:
    """DeepSeek 批量评级客户端"""

    # 429 限流参数
    MAX_BACKOFF = 120          # 最大退避等待秒数
    INITIAL_BACKOFF = 2        # 初始退避秒数
    BACKOFF_MULTIPLIER = 2     # 退避倍数
    MAX_429_RETRIES = 50       # 单次调用429最大重试次数
    TPM_ADAPT_STEP = 0.5       # TPM自适应: 每次增加的额外延迟(秒)
    TPM_MAX_EXTRA_DELAY = 10   # TPM自适应: 最大额外延迟(秒)

    def __init__(self, api_key: str, prompt_template_path: str = "engine/prompts/analysis_prompt.md",
                 base_url: str = "https://api.deepseek.com/v1",
                 model: str = "deepseek-v4-flash", temperature: float = 0.1,
                 max_tokens: int = 8000, timeout: int = 120,
                 batch_size: int = 3, rate_limit: float = 0.5,
                 progress_file: str = "data/.llm_progress.json"):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.batch_size = batch_size
        self.rate_limit = rate_limit
        self.progress_file = progress_file
        with open(prompt_template_path, "r", encoding="utf-8") as f:
            self.prompt_template = f.read()
        self.few_shot_examples = []
        try:
            few_shot_path = prompt_template_path.replace("analysis_prompt.md", "few_shot_examples.json")
            with open(few_shot_path, "r", encoding="utf-8") as f:
                self.few_shot_examples = json.load(f)
        except FileNotFoundError:
            pass

        # TPM 自适应状态
        self._extra_delay = 0.0     # 额外延迟 (429后自动增加)
        self._consecutive_429 = 0   # 连续429计数
        self._consecutive_ok = 0    # 连续成功计数

    # ================================================================
    # 进度持久化 (断点续跑)
    # ================================================================

    def _load_progress(self, mode: str) -> set:
        """加载已完成的 company_id 集合"""
        if not os.path.exists(self.progress_file):
            return set()
        try:
            with open(self.progress_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return set(data.get(mode, []))
        except (json.JSONDecodeError, KeyError):
            return set()

    def _save_progress(self, mode: str, completed_ids: set):
        """保存进度到文件"""
        os.makedirs(os.path.dirname(self.progress_file) or ".", exist_ok=True)
        try:
            # 读取现有进度
            data = {}
            if os.path.exists(self.progress_file):
                with open(self.progress_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data[mode] = list(completed_ids)
            with open(self.progress_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"保存进度失败: {e}")

    def _clear_progress(self, mode: str):
        """清除指定模式的进度 (全量完成或手动清理)"""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data.pop(mode, None)
                with open(self.progress_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
            except Exception:
                pass

    # ================================================================
    # 批量评级 (主入口)
    # ================================================================

    def batch_rate(self, companies: List[Dict], mode: str = "incremental") -> List[Dict]:
        """批量评级 — 支持429自动续跑 + 断点续跑

        Args:
            companies: 企业列表，每个dict需含 company_id
            mode: 评级模式，用于进度文件key

        Returns:
            成功评级的企业列表
        """
        # 断点续跑: 跳过已完成的企业
        completed_ids = self._load_progress(mode)
        if completed_ids:
            logger.info(f"断点续跑: 已有 {len(completed_ids)} 家企业完成，跳过")
            remaining = [c for c in companies if c.get("company_id") not in completed_ids]
            logger.info(f"剩余待评级: {len(remaining)} 家 (总共 {len(companies)} 家)")
            companies = remaining

        results = []
        total_batches = (len(companies) + self.batch_size - 1) // self.batch_size

        for i in range(0, len(companies), self.batch_size):
            batch_num = i // self.batch_size + 1
            batch = companies[i:i + self.batch_size]
            batch_ids = [c.get("company_id") for c in batch]

            logger.info(f"批次 {batch_num}/{total_batches}: 评级企业 {batch_ids}")

            prompt = self._build_batch_prompt(batch)
            response_text = self._call_llm_with_retry(prompt)

            if response_text:
                parsed = self._parse_response(response_text, batch)
                results.extend(parsed)

                # 标记批次中的企业为已完成 (即使部分解析失败也标记，避免卡在同一条)
                for cid in batch_ids:
                    if cid is not None:
                        completed_ids.add(cid)
                self._save_progress(mode, completed_ids)

                logger.info(f"批次 {batch_num} 完成: 解析 {len(parsed)} 条结果")
            else:
                # API调用彻底失败 (超过最大重试)，记录并继续
                logger.error(f"批次 {batch_num} 失败: 企业 {batch_ids} 将在下次重跑时重试")

            # 限速: 基础 + TPM自适应额外延迟
            sleep_time = self.rate_limit + self._extra_delay
            if sleep_time > 0:
                time.sleep(sleep_time)

        # 全部完成后清除进度文件
        if len(companies) > 0 and len(completed_ids) >= len(companies):
            self._clear_progress(mode)
            logger.info("全部评级完成，已清除进度文件")

        return results

    # ================================================================
    # DeepSeek API 调用 (429增强)
    # ================================================================

    def _call_llm(self, prompt: str, retries_5xx: int = 3) -> str:
        """调用DeepSeek API — 基础版本 (不包含429自动重试)"""
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "response_format": {"type": "json_object"},
                },
                timeout=self.timeout,
            )
            return resp
        except requests.Timeout:
            logger.error("API超时")
            return None
        except Exception as e:
            logger.error(f"API调用异常: {e}")
            return None

    def _call_llm_with_retry(self, prompt: str) -> Optional[str]:
        """调用DeepSeek API — 429自适应重试 + 指数退避

        核心策略:
        1. 遇到429: 指数退避等待，最多重试 MAX_429_RETRIES 次
        2. TPM自适应: 连续429时增加额外延迟，连续成功时减少
        3. 遇到5xx: 重试3次
        4. 其他错误: 直接返回None
        """
        wait_time = self.INITIAL_BACKOFF
        retries_5xx = 3

        for attempt in range(self.MAX_429_RETRIES + 1):
            raw_resp = self._call_llm(prompt)

            # 网络异常
            if raw_resp is None:
                return None

            # 已经是 response 对象
            resp = raw_resp

            # 200 成功
            if resp.status_code == 200:
                self._on_success()
                try:
                    return resp.json()["choices"][0]["message"]["content"]
                except (KeyError, IndexError, json.JSONDecodeError) as e:
                    logger.error(f"解析200响应失败: {e}")
                    return None

            # 429 TPM限流 — 自适应退避
            elif resp.status_code == 429:
                self._on_429()
                logger.warning(
                    f"429 TPM限流 (第{attempt+1}次重试), "
                    f"等待{wait_time}秒, 当前额外延迟={self._extra_delay:.1f}s"
                )
                time.sleep(wait_time)
                wait_time = min(wait_time * self.BACKOFF_MULTIPLIER, self.MAX_BACKOFF)
                continue

            # 5xx 服务端错误
            elif resp.status_code >= 500:
                retries_5xx -= 1
                if retries_5xx <= 0:
                    logger.error("5xx连续3次失败")
                    return None
                logger.warning(f"5xx错误 (剩余重试{retries_5xx}): {resp.status_code}")
                time.sleep(5)
                continue

            # 其他错误
            else:
                logger.error(f"API异常: {resp.status_code}, body={resp.text[:200]}")
                return None

        # 超过最大重试次数
        logger.error(f"429重试 {self.MAX_429_RETRIES} 次后仍然失败，放弃本批次")
        return None

    # ================================================================
    # TPM 自适应控制
    # ================================================================

    def _on_429(self):
        """429事件: 增加额外延迟"""
        self._consecutive_429 += 1
        self._consecutive_ok = 0
        # 每次连续429增加延迟
        self._extra_delay = min(
            self._extra_delay + self.TPM_ADAPT_STEP * self._consecutive_429,
            self.TPM_MAX_EXTRA_DELAY
        )
        logger.info(f"TPM自适应: 额外延迟增至 {self._extra_delay:.1f}s (连续429: {self._consecutive_429})")

    def _on_success(self):
        """成功事件: 逐步减少额外延迟"""
        self._consecutive_ok += 1
        self._consecutive_429 = 0
        # 连续3次成功后开始减少延迟
        if self._consecutive_ok >= 3 and self._extra_delay > 0:
            self._extra_delay = max(0, self._extra_delay - self.TPM_ADAPT_STEP)
            logger.debug(f"TPM自适应: 额外延迟减至 {self._extra_delay:.1f}s")

    # ================================================================
    # Prompt 构建
    # ================================================================

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

    # ================================================================
    # 响应解析
    # ================================================================

    def _parse_response(self, response: str, batch: List[Dict]) -> List[Dict]:
        """解析DeepSeek返回的JSON，支持多种格式"""
        # 尝试从markdown代码块中提取JSON
        json_str = response.strip()
        if "```json" in json_str:
            start = json_str.find("```json") + 7
            end = json_str.find("```", start)
            if end > start:
                json_str = json_str[start:end].strip()
        elif "```" in json_str:
            start = json_str.find("```") + 3
            end = json_str.find("```", start)
            if end > start:
                json_str = json_str[start:end].strip()

        try:
            data = json.loads(json_str)
            if isinstance(data, dict):
                # 单个结果，包装为列表
                data = [data]
            results = data if isinstance(data, list) else []
            # 补充 company_id (DeepSeek可能不返回)
            for i, r in enumerate(results):
                if "company_id" not in r and i < len(batch):
                    r["company_id"] = batch[i].get("company_id")
            return [r for r in results if self._validate_result(r)]
        except json.JSONDecodeError:
            logger.warning(f"JSON解析失败, 原始响应: {response[:200]}")
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

    # ================================================================
    # 数据库更新
    # ================================================================

    def update_database(self, results: List[Dict], database_url: str):
        import psycopg2

        if not results:
            logger.warning("results 为空，跳过数据库更新")
            return

        conn = None
        try:
            conn = psycopg2.connect(database_url)
            cur = conn.cursor()

            success_ids = []
            failed_ids = []

            for result in results:
                company_id = result.get("company_id")
                if company_id is None:
                    logger.warning(f"结果缺少 company_id，跳过: {result}")
                    continue
                try:
                    cur.execute(
                        """
                        INSERT INTO ratings
                            (company_id, total_score, rating_level, demand_tags, sales_pitch, reasoning, rated_by, rated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (company_id, rated_by) DO UPDATE SET
                            total_score = EXCLUDED.total_score,
                            rating_level = EXCLUDED.rating_level,
                            demand_tags = EXCLUDED.demand_tags,
                            sales_pitch = EXCLUDED.sales_pitch,
                            reasoning = EXCLUDED.reasoning,
                            rated_at = NOW()
                        """,
                        (
                            company_id,
                            result.get("score"),
                            result.get("level"),
                            result.get("demand_tags"),  # 列表 → psycopg2 自动适配 TEXT[]
                            result.get("sales_pitch"),
                            result.get("reasoning"),
                            "deepseek",
                        ),
                    )
                    success_ids.append(company_id)
                except Exception as e:
                    logger.error(f"写入 ratings 失败, company_id={company_id}: {e}")
                    failed_ids.append(company_id)

            # 更新 companies 状态
            if success_ids:
                cur.execute(
                    "UPDATE companies SET status = 'rated' WHERE id = ANY(%s)",
                    (success_ids,),
                )
                logger.info(f"已将 {len(success_ids)} 家企业状态更新为 rated: {success_ids}")

            if failed_ids:
                cur.execute(
                    "UPDATE companies SET status = 'retry' WHERE id = ANY(%s)",
                    (failed_ids,),
                )
                logger.warning(f"已将 {len(failed_ids)} 家企业状态更新为 retry: {failed_ids}")

            conn.commit()
            logger.info(f"数据库更新完成: 成功 {len(success_ids)}, 失败 {len(failed_ids)}")

        except Exception as e:
            logger.error(f"数据库更新异常: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()


if __name__ == "__main__":
    from dotenv import load_dotenv
    import os
    load_dotenv()
    client = LLMRatingClient(api_key=os.getenv("DEEPSEEK_API_KEY", ""))
    print("DeepSeek客户端就绪 (增强版: 429自适应退避 + 断点续跑)")
