"""报告生成 + 销售线索导出"""

import csv
import json
import logging
import os
from datetime import date, timedelta

import psycopg2

logger = logging.getLogger(__name__)


class ReportGenerator:
    """评级报告生成和线索导出"""

    def __init__(self, database_url: str, output_dir: str = "data/reports"):
        self.database_url = database_url
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 数据库辅助
    # ------------------------------------------------------------------

    def _get_connection(self):
        return psycopg2.connect(self.database_url)

    @staticmethod
    def _rows_to_dicts(cur) -> list:
        """将 psycopg2 cursor 结果转为 dict 列表"""
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # 1. 日报生成
    # ------------------------------------------------------------------

    def generate_daily(self, report_date: date = None) -> str:
        """生成每日评级报告 (Markdown)

        Args:
            report_date: 报告日期，默认为今天

        Returns:
            生成的报告文件路径
        """
        if report_date is None:
            report_date = date.today()

        conn = self._get_connection()
        try:
            ratings = self._query_ratings_by_date(conn, report_date)
        finally:
            conn.close()

        if not ratings:
            logger.warning(f"{report_date} 无评级数据，跳过日报生成")
            return ""

        # 评级分布统计
        distribution = {"S": 0, "A": 0, "B": 0, "C": 0, "D": 0}
        for r in ratings:
            level = r.get("rating_level", "D")
            if level in distribution:
                distribution[level] += 1

        # S/A 级企业详情
        sa_enterprises = [
            r for r in ratings if r.get("rating_level") in ("S", "A")
        ]

        # 组装 Markdown
        md_lines = self._build_daily_markdown(report_date, distribution, sa_enterprises, len(ratings))
        output_path = os.path.join(self.output_dir, f"daily_{report_date}.md")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        logger.info(f"日报已生成: {output_path}")
        return output_path

    def _query_ratings_by_date(self, conn, report_date: date) -> list:
        """查询指定日期的评级记录 (含企业信息)"""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    r.id AS rating_id,
                    r.company_id,
                    r.total_score,
                    r.rating_level,
                    r.tech_score,
                    r.funding_score,
                    r.intent_score,
                    r.team_score,
                    r.industry_score,
                    r.demand_tags,
                    r.sales_pitch,
                    r.reasoning,
                    r.rated_by,
                    r.rated_at,
                    c.company_name,
                    c.credit_code,
                    c.business_scope,
                    c.industry_tags
                FROM ratings r
                JOIN companies c ON r.company_id = c.id
                WHERE DATE(r.rated_at) = %s
                ORDER BY r.total_score DESC
                """,
                (report_date,),
            )
            return self._rows_to_dicts(cur)

    def _build_daily_markdown(self, report_date: date, distribution: dict,
                              sa_enterprises: list, total: int) -> list:
        """构建日报 Markdown 内容行"""
        lines = [
            f"# 每日评级报告 — {report_date}",
            "",
            "## 评级分布",
            "",
            "| 等级 | 数量 | 占比 |",
            "|------|------|------|",
        ]
        for level in ("S", "A", "B", "C", "D"):
            count = distribution[level]
            pct = f"{count / total * 100:.1f}%" if total > 0 else "0.0%"
            lines.append(f"| {level} | {count} | {pct} |")
        lines.append(f"| **合计** | **{total}** | **100%** |")

        if sa_enterprises:
            lines.extend([
                "",
                "## S/A 级企业详情",
                "",
            ])
            for ent in sa_enterprises:
                demand_tags = self._format_list_field(ent.get("demand_tags"))
                sales_pitch = ent.get("sales_pitch") or "—"
                reasoning = ent.get("reasoning") or "—"

                lines.extend([
                    f"### {ent['company_name']}",
                    f"- **评分**: {ent['total_score']} 分",
                    f"- **等级**: {ent['rating_level']}",
                    f"- **需求标签**: {demand_tags}",
                    f"- **销售话术**: {sales_pitch}",
                    f"- **评级理由**: {reasoning}",
                    "",
                ])

        lines.extend([
            "",
            "---",
            f"*报告生成时间: {date.today()}*",
        ])
        return lines

    # ------------------------------------------------------------------
    # 2. 线索导出
    # ------------------------------------------------------------------

    def export_leads(self, levels=None, output_path: str = None) -> str:
        """导出评级企业线索 (CSV + Excel) — 支持与已有文件合并

        核心逻辑:
        1. 从数据库查询指定等级的企业 (默认全量 S/A/B/C/D)
        2. 如已有CSV文件，按 credit_code 合并 (新数据覆盖旧数据)
        3. 写入固定的文件名 all_rated_companies.csv/.xlsx

        Args:
            levels: 评级等级列表，默认 ["S", "A", "B", "C", "D"]
            output_path: 输出路径前缀 (不含扩展名)，默认固定文件名

        Returns:
            CSV 文件路径
        """
        if levels is None:
            levels = ["S", "A", "B", "C", "D"]

        conn = self._get_connection()
        try:
            data = self._query_leads(conn, levels)
        finally:
            conn.close()

        if not data:
            logger.warning(f"等级 {levels} 无线索数据")
            return ""

        # 处理 list/dict 字段为逗号分隔字符串
        data = [self._flatten_row(row) for row in data]

        # 固定文件名
        base = output_path or os.path.join(self.output_dir, "all_rated_companies")
        csv_path = f"{base}.csv"
        xlsx_path = f"{base}.xlsx"

        # 合并已有数据
        merged = self._merge_with_existing(data, csv_path)

        self.export_csv(merged, csv_path)
        self.export_excel(merged, xlsx_path)

        logger.info(f"线索已导出(合并): {csv_path}, {xlsx_path}, 共{len(merged)}条")
        return csv_path

    def _query_leads(self, conn, levels: list) -> list:
        """查询指定等级的线索数据 (含分项分数+爬取时间)

        每个企业只取最高分的一条评级记录 (PostgreSQL DISTINCT ON)
        """
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (c.id)
                    c.company_name,
                    c.credit_code,
                    c.registered_capital,
                    c.business_scope,
                    c.industry_tags,
                    c.registered_address,
                    c.funding_stage,
                    r.total_score,
                    r.rating_level,
                    r.tech_score,
                    r.funding_score,
                    r.intent_score,
                    r.team_score,
                    r.industry_score,
                    r.demand_tags,
                    r.sales_pitch,
                    r.reasoning,
                    r.rated_at AS crawl_time
                FROM ratings r
                JOIN companies c ON r.company_id = c.id
                WHERE r.rating_level IN %s
                ORDER BY c.id, r.total_score DESC, r.rated_at DESC
                """,
                (tuple(levels),),
            )
            return self._rows_to_dicts(cur)

    # ------------------------------------------------------------------
    # 3. CSV 导出
    # ------------------------------------------------------------------

    def export_csv(self, data: list, output_path: str) -> str:
        """导出数据为 CSV (UTF-8 BOM)

        Args:
            data: dict 列表
            output_path: 输出文件路径

        Returns:
            输出文件路径
        """
        if not data:
            return output_path

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)

        logger.info(f"CSV 已导出: {output_path}")
        return output_path

    # ------------------------------------------------------------------
    # 4. Excel 导出
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # 5. CSV 合并 (按 credit_code 去重覆盖)
    # ------------------------------------------------------------------

    def _merge_with_existing(self, new_data: list, csv_path: str) -> list:
        """读取已有CSV，按credit_code合并 — 新数据覆盖旧数据，保留不在新数据中的历史企业

        Args:
            new_data: 本次从数据库查询并展平后的数据 (dict 列表)
            csv_path: 已有的CSV文件路径

        Returns:
            合并后的 dict 列表 (按 total_score 降序)
        """
        if not os.path.exists(csv_path):
            return new_data

        try:
            existing = []
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                existing = list(reader)

            if not existing:
                return new_data

            # 按 credit_code 建立索引
            by_code = {}
            for row in existing:
                code = row.get("credit_code", "").strip()
                if code:
                    by_code[code] = row

            # 新数据覆盖旧数据
            for row in new_data:
                code = row.get("credit_code", "").strip()
                if code:
                    by_code[code] = row
                else:
                    # 无 credit_code 的记录也加入 (用 company_name 去重)
                    name = row.get("company_name", "")
                    if name and not any(r.get("company_name") == name for r in by_code.values()):
                        by_code[f"__name__{name}"] = row

            # 按评分降序
            merged = list(by_code.values())
            merged.sort(
                key=lambda x: int(x.get("total_score") or 0),
                reverse=True,
            )
            return merged

        except Exception as e:
            logger.warning(f"合并已有CSV失败，使用新数据: {e}")
            return new_data

    def export_excel(self, data: list, output_path: str) -> str:
        """导出数据为 Excel (openpyxl, 格式化表头)

        Args:
            data: dict 列表
            output_path: 输出文件路径 (.xlsx)

        Returns:
            输出文件路径
        """
        if not data:
            return output_path

        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        wb = Workbook()
        ws = wb.active
        ws.title = "销售线索"

        fieldnames = list(data[0].keys())

        # 表头样式: 蓝色背景 + 白色粗体
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(name="微软雅黑", bold=True, color="FFFFFF", size=11)
        header_alignment = Alignment(horizontal="center", vertical="center")

        for col_idx, field in enumerate(fieldnames, 1):
            cell = ws.cell(row=1, column=col_idx, value=field)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_alignment

        # 数据行
        for row_idx, row in enumerate(data, 2):
            for col_idx, field in enumerate(fieldnames, 1):
                ws.cell(row=row_idx, column=col_idx, value=row.get(field, ""))

        # 自动列宽
        for col_idx, field in enumerate(fieldnames, 1):
            max_len = len(str(field))
            for row_idx in range(2, len(data) + 2):
                cell_value = str(data[row_idx - 2].get(field, ""))
                max_len = max(max_len, len(cell_value))
            # 中文字符宽度约为英文的 2 倍，取字符数作为近似
            adjusted_width = min(max_len + 4, 50)
            col_letter = ws.cell(row=1, column=col_idx).column_letter
            ws.column_dimensions[col_letter].width = adjusted_width

        wb.save(output_path)
        logger.info(f"Excel 已导出: {output_path}")
        return output_path

    # ------------------------------------------------------------------
    # 5. 新线索通知
    # ------------------------------------------------------------------

    def notify_new_leads(self, new_leads: list) -> str:
        """比较昨日评级，发现新晋升的 S/A 企业并生成通知

        Args:
            new_leads: 当日 S/A 级评级结果列表 (dict, 含 company_id)

        Returns:
            通知文本
        """
        if not new_leads:
            return "今日无新 S/A 级线索。"

        yesterday = date.today() - timedelta(days=1)

        conn = self._get_connection()
        try:
            yesterday_sa_ids = self._get_sa_company_ids(conn, yesterday)
        finally:
            conn.close()

        # 筛选出昨日不是 S/A 的企业 — 即新晋升者
        newly_upgraded = [
            lead for lead in new_leads
            if lead.get("company_id") not in yesterday_sa_ids
        ]

        if not newly_upgraded:
            return "今日无新晋升 S/A 级企业。"

        # 生成通知文本
        lines = [
            f"=== 新线索通知 ({date.today()}) ===",
            f"发现 {len(newly_upgraded)} 家企业新晋升为 S/A 级：",
            "",
        ]
        for lead in newly_upgraded:
            name = lead.get("company_name", "未知")
            score = lead.get("total_score", lead.get("score", "?"))
            level = lead.get("rating_level", lead.get("level", "?"))
            tags = self._format_list_field(lead.get("demand_tags"))
            lines.append(f"- {name} | 评分: {score} | 等级: {level} | 需求: {tags}")

        # 更新 companies.status = 'filtered'
        company_ids = [lead["company_id"] for lead in newly_upgraded if lead.get("company_id")]
        if company_ids:
            self._update_status_filtered(company_ids)

        notification = "\n".join(lines)
        logger.info(f"新线索通知: {len(newly_upgraded)} 家企业")
        return notification

    def _get_sa_company_ids(self, conn, target_date: date) -> set:
        """获取指定日期的 S/A 级企业 ID 集合"""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT r.company_id
                FROM ratings r
                WHERE r.rating_level IN ('S', 'A')
                  AND DATE(r.rated_at) = %s
                """,
                (target_date,),
            )
            return {row[0] for row in cur.fetchall()}

    def _update_status_filtered(self, company_ids: list):
        """将指定企业状态更新为 filtered"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE companies SET status = 'filtered', updated_at = NOW() WHERE id = ANY(%s)",
                    (company_ids,),
                )
            conn.commit()
            logger.info(f"已将 {len(company_ids)} 家企业状态更新为 filtered")
        except Exception as e:
            logger.error(f"更新 filtered 状态失败: {e}")
            conn.rollback()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _format_list_field(value) -> str:
        """将 list/dict/JSON 字符串字段格式化为逗号分隔字符串"""
        if value is None:
            return "—"
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        if isinstance(value, dict):
            return ", ".join(f"{k}: {v}" for k, v in value.items())
        if isinstance(value, str):
            # 尝试解析 JSON 字符串
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return ", ".join(str(v) for v in parsed)
                if isinstance(parsed, dict):
                    return ", ".join(f"{k}: {v}" for k, v in parsed.items())
            except (json.JSONDecodeError, TypeError):
                pass
            return value
        return str(value)

    @staticmethod
    def _flatten_row(row: dict) -> dict:
        """将行数据中的 list/dict 字段转换为逗号分隔字符串"""
        flat = {}
        for key, value in row.items():
            flat[key] = ReportGenerator._format_list_field(value)
        return flat


# ======================================================================
# CLI 入口
# ======================================================================

if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(description="评级报告生成器")
    parser.add_argument("--date", default=str(date.today()), help="报告日期 (YYYY-MM-DD)")
    parser.add_argument(
        "--mode",
        default="daily",
        choices=["daily", "leads", "notify"],
        help="运行模式: daily(日报), leads(线索导出), notify(新线索通知)",
    )
    parser.add_argument("--levels", default="S,A,B,C,D", help="线索导出等级，逗号分隔 (默认: S,A,B,C,D)")
    parser.add_argument("--output", default=None, help="输出文件路径前缀 (leads 模式，默认: all_rated_companies)")

    args = parser.parse_args()

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        print("错误: 请设置 DATABASE_URL 环境变量")
        exit(1)

    gen = ReportGenerator(database_url=db_url)

    report_date = date.fromisoformat(args.date)

    if args.mode == "daily":
        path = gen.generate_daily(report_date)
        if path:
            print(f"日报已生成: {path}")
        else:
            print(f"{report_date} 无评级数据，未生成日报")

    elif args.mode == "leads":
        levels = [l.strip().upper() for l in args.levels.split(",")]
        path = gen.export_leads(levels=levels, output_path=args.output)
        if path:
            print(f"线索已导出: {path}")
        else:
            print(f"等级 {levels} 无线索数据")

    elif args.mode == "notify":
        # 查询当日 S/A 级评级数据用于通知
        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT r.company_id, r.total_score, r.rating_level,
                           r.demand_tags, c.company_name
                    FROM ratings r
                    JOIN companies c ON r.company_id = c.id
                    WHERE r.rating_level IN ('S', 'A')
                      AND DATE(r.rated_at) = %s
                    ORDER BY r.total_score DESC
                    """,
                    (report_date,),
                )
                columns = [desc[0] for desc in cur.description]
                today_sa = [dict(zip(columns, row)) for row in cur.fetchall()]
        finally:
            conn.close()

        notification = gen.notify_new_leads(today_sa)
        print(notification)
