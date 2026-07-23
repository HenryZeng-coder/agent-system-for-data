"""管道入口 — 实际管道在 pipelines/ 子目录中"""

# 5级管道在 pipelines/ 子目录中按优先级注册:
# dedup_pipeline.py     (100) — 去重
# filter_pipeline.py    (200) — IT行业过滤
# clean_pipeline.py     (300) — 数据清洗
# validate_pipeline.py  (400) — 完整性验证
# standardize_pipeline.py (500) — 格式标准化 + 数据库写入
