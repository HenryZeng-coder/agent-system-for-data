import sys,os
sys.path.insert(0,os.path.join(os.path.dirname(__file__),".."))
from engine.llm_client import LLMRatingClient, parse_levels, ALL_LEVELS

class TestLLM:
    def _c(self):
        c=LLMRatingClient.__new__(LLMRatingClient)
        return c
    def test_valid(self):
        assert self._c()._validate_result({"score":82,"level":"A","demand_tags":["AI"]}) is True
    def test_bad_level(self):
        assert self._c()._validate_result({"score":82,"level":"X","demand_tags":["AI"]}) is False
    def test_bad_score(self):
        assert self._c()._validate_result({"score":150,"level":"A","demand_tags":["AI"]}) is False


class TestParseLevels:
    """--levels 参数解析 (热点追踪按等级重评)"""

    def test_none_and_empty(self):
        assert parse_levels(None) == []
        assert parse_levels("") == []
        assert parse_levels([]) == []

    def test_single(self):
        assert parse_levels("S") == ["S"]
        assert parse_levels("a") == ["A"]          # 小写归一化

    def test_multiple_sorted(self):
        # 传入顺序无关, 返回值固定按 S>A>B>C>D
        assert parse_levels("A,S") == ["S", "A"]
        assert parse_levels("d,c,b,a,s") == list(ALL_LEVELS)

    def test_fullwidth_comma_and_spaces(self):
        assert parse_levels(" S ， A ") == ["S", "A"]

    def test_invalid_dropped(self):
        assert parse_levels("S,X,") == ["S"]
        assert parse_levels("1,2") == []

    def test_list_input(self):
        assert parse_levels(["S", "A"]) == ["S", "A"]

    def test_all_levels_constant(self):
        assert ALL_LEVELS == ("S", "A", "B", "C", "D")
