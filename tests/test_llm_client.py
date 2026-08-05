import sys,os
sys.path.insert(0,os.path.join(os.path.dirname(__file__),".."))
from engine.llm_client import LLMRatingClient

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
