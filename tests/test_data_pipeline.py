import sys,os
sys.path.insert(0,os.path.join(os.path.dirname(__file__),".."))
from engine.data_pipeline import DataPipeline

class TestDataPipeline:
    def test_dedup(self):
        p=DataPipeline()
        d=[{"credit_code":"A"},{"credit_code":"A"},{"credit_code":"B"}]
        assert len(p.deduplicate(d))==2
    def test_empty(self):
        assert DataPipeline().run([])==[]
