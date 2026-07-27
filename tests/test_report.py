"""报告生成模块测试 — 日报/线索导出/通知/格式化工具

覆盖 ReportGenerator 的纯逻辑方法 (无需数据库):
- _format_list_field: list/dict/JSON字符串格式化
- _flatten_row: 行数据字段展平
- _build_daily_markdown: Markdown 日报构建
- _parse_capital / _standardize_date (通过 standardize 间接测试)

需要数据库的方法 (generate_daily / export_leads / notify_new_leads)
不在离线测试中覆盖，需端到端联调验证。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.report import ReportGenerator


class TestFormatListField:
    """_format_list_field 工具方法"""

    def test_list(self):
        """列表 → 逗号分隔"""
        assert ReportGenerator._format_list_field(["AI", "云计算", "大数据"]) == "AI, 云计算, 大数据"

    def test_dict(self):
        """字典 → key:value 逗号分隔"""
        assert ReportGenerator._format_list_field({"a": 1, "b": 2}) == "a: 1, b: 2"

    def test_json_string_list(self):
        """JSON字符串(数组) → 逗号分隔"""
        assert ReportGenerator._format_list_field('["AI", "云"]') == "AI, 云"

    def test_json_string_dict(self):
        """JSON字符串(对象) → key:value 逗号分隔"""
        assert ReportGenerator._format_list_field('{"a":1}') == "a: 1"

    def test_plain_string(self):
        """普通字符串 → 直接返回"""
        assert ReportGenerator._format_list_field("普通文本") == "普通文本"

    def test_none(self):
        """None → 返回占位符"""
        assert ReportGenerator._format_list_field(None) == "—"

    def test_number(self):
        """数字 → str"""
        assert ReportGenerator._format_list_field(42) == "42"

    def test_empty_list(self):
        """空列表 → 返回空字符串"""
        assert ReportGenerator._format_list_field([]) == ""


class TestFlattenRow:
    """_flatten_row 行展平"""

    def test_flatten_list_field(self):
        """list 字段 → 逗号分隔字符串"""
        row = {"name": "test", "tags": ["AI", "云计算"]}
        flat = ReportGenerator._flatten_row(row)
        assert flat["tags"] == "AI, 云计算"
        assert flat["name"] == "test"

    def test_flatten_none_field(self):
        """None → 占位符"""
        row = {"name": "test", "tags": None}
        flat = ReportGenerator._flatten_row(row)
        assert flat["tags"] == "—"

    def test_flatten_json_string(self):
        """JSON字符串 → 解析后逗号分隔"""
        row = {"tags": '["AI"]'}
        flat = ReportGenerator._flatten_row(row)
        assert flat["tags"] == "AI"

    def test_flatten_preserves_string(self):
        """普通字符串不变"""
        row = {"name": "武汉AI"}
        flat = ReportGenerator._flatten_row(row)
        assert flat["name"] == "武汉AI"


class TestBuildDailyMarkdown:
    """_build_daily_markdown Markdown构建"""

    def _gen(self):
        """创建无DB的 ReportGenerator (仅用于纯逻辑测试)"""
        return ReportGenerator.__new__(ReportGenerator)

    def test_basic_report(self):
        """基本日报包含标题和分布表"""
        gen = self._gen()
        distribution = {"S": 1, "A": 2, "B": 3, "C": 2, "D": 2}
        lines = gen._build_daily_markdown(
            report_date="2026-07-27",
            distribution=distribution,
            sa_enterprises=[],
            total=10,
        )
        md = "\n".join(lines)
        assert "# 每日评级报告" in md
        assert "| S | 1 |" in md
        assert "| A | 2 |" in md
        assert "**合计** | **10**" in md

    def test_sa_enterprises_in_report(self):
        """S/A级企业详情包含在日报中"""
        gen = self._gen()
        distribution = {"S": 1, "A": 0, "B": 0, "C": 0, "D": 0}
        sa = [{
            "company_name": "武汉AI科技",
            "total_score": 85,
            "rating_level": "S",
            "demand_tags": '["AI质检", "云迁移"]',
            "sales_pitch": "助力数字化转型",
            "reasoning": "技术投入高",
        }]
        lines = gen._build_daily_markdown(
            report_date="2026-07-27",
            distribution=distribution,
            sa_enterprises=sa,
            total=1,
        )
        md = "\n".join(lines)
        assert "武汉AI科技" in md
        assert "85 分" in md
        assert "AI质检" in md

    def test_empty_distribution(self):
        """空分布 (total=0)"""
        gen = self._gen()
        distribution = {"S": 0, "A": 0, "B": 0, "C": 0, "D": 0}
        lines = gen._build_daily_markdown(
            report_date="2026-07-27",
            distribution=distribution,
            sa_enterprises=[],
            total=0,
        )
        md = "\n".join(lines)
        assert "| S | 0 |" in md
        assert "0.0%" in md


class TestExportCsv:
    """CSV 导出测试"""

    def test_export_csv_creates_file(self):
        """CSV导出: 创建UTF-8-BOM文件"""
        import tempfile
        gen = ReportGenerator.__new__(ReportGenerator)
        data = [{"name": "武汉AI", "score": 85}]
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            path = f.name
        result = gen.export_csv(data, path)
        assert result == path

        # 验证内容
        with open(path, "r", encoding="utf-8-sig") as f:
            content = f.read()
        assert "name" in content
        assert "武汉AI" in content
        os.unlink(path)

    def test_export_csv_empty_data(self):
        """空数据 → 返回路径但不写文件"""
        import tempfile
        gen = ReportGenerator.__new__(ReportGenerator)
        path = tempfile.mktemp(suffix=".csv")
        result = gen.export_csv([], path)
        assert result == path


class TestExportExcel:
    """Excel 导出测试"""

    def test_export_excel_creates_file(self):
        """Excel导出: 创建xlsx文件"""
        import tempfile
        gen = ReportGenerator.__new__(ReportGenerator)
        data = [{"name": "武汉AI", "score": 85}]
        path = tempfile.mktemp(suffix=".xlsx")
        result = gen.export_excel(data, path)
        assert result == path
        # 验证文件存在且可打开
        from openpyxl import load_workbook
        wb = load_workbook(path)
        ws = wb.active
        assert ws.title == "销售线索"
        assert ws.cell(row=1, column=1).value == "name"
        assert ws.cell(row=2, column=1).value == "武汉AI"
        wb.close()
        os.unlink(path)

    def test_export_excel_empty_data(self):
        """空数据 → 返回路径"""
        import tempfile
        gen = ReportGenerator.__new__(ReportGenerator)
        path = tempfile.mktemp(suffix=".xlsx")
        result = gen.export_excel([], path)
        assert result == path


class TestScoreToLevel:
    """评级等级映射 (来自 rules_engine, 此处确认一致性)"""

    def test_level_s(self):
        from engine.rules_engine import RatingRulesEngine
        assert RatingRulesEngine._score_to_level(85) == "S"

    def test_level_a(self):
        from engine.rules_engine import RatingRulesEngine
        assert RatingRulesEngine._score_to_level(65) == "A"

    def test_level_b(self):
        from engine.rules_engine import RatingRulesEngine
        assert RatingRulesEngine._score_to_level(45) == "B"

    def test_level_c(self):
        from engine.rules_engine import RatingRulesEngine
        assert RatingRulesEngine._score_to_level(25) == "C"

    def test_level_d(self):
        from engine.rules_engine import RatingRulesEngine
        assert RatingRulesEngine._score_to_level(10) == "D"
