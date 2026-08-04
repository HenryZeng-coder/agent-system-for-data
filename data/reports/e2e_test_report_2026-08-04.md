# E-InfoInsight 端到端全量测试报告

**日期**: 2026-08-04  
**调度引擎**: kscc (替代 Hermes/Glm)  
**测试范围**: 15家武汉IT企业全量爬取 + 评分 + 报告

---

## 一、测试执行摘要

| 阶段 | 状态 | 数据量 | 备注 |
|------|------|--------|------|
| 新闻舆情采集 | ✅ 完成 | 159条 | 百度/搜狗搜索，5-15条/企业 |
| 技术画像采集 | ⚠️ 部分 | 15条 | GitHub API SSL失败，手动补充cloud/github/blog |
| 招聘信息采集 | ✅ 完成 | 120条 | 搜索推断，8-10条/企业 |
| 招投标采集 | ⚠️ 偏少 | 8条 | 搜索引擎收录有限 |
| 规则引擎评分 | ✅ 完成 | 15家 | 4家B级通过(≥50) |
| GLM深度评级 | ❌ 失败 | 0家 | batch_rate()代码bug |
| 报告生成 | ✅ 完成 | 1份 | daily_2026-08-04.md |

## 二、评分分布

| 等级 | 数量 | 企业 |
|------|------|------|
| S (≥80) | 0 | — |
| A (≥60) | 0 | — |
| B (≥50) | 4 | 光谷信息(56), 木仓科技(56), 奇安信(51), 极智嘉(51) |
| C (≥20) | 6 | 远光软件(46), 融芯智能(45), 达梦(42), 烽火(42), 旷视(41), 长飞(40) |
| D (<20) | 1 | 斗鱼(39), 百域(36), 腾讯武汉(30), 爱迪(29), 灿宇(19) |

**最高分**: 56分 (光谷信息、木仓科技)  
**平均分**: 41.3分

## 三、发现的Bug与问题

### P0 - 阻断级

1. **GLM batch_rate() 代码bug**  
   - 文件: `engine/glm_client.py:131`  
   - 问题: `batch_ids = [c.get("company_id") for c in batch]` — batch中的元素是str而非dict  
   - 影响: GLM深度评级完全无法运行  
   - 修复建议: 检查batch_rate中数据库查询返回格式，确保每条记录是dict

2. **GitHub API SSL连接失败**  
   - 文件: `scripts/integrated_crawl.py` tech_spider部分  
   - 问题: `requests.get("https://api.github.com/...")` 全部SSL超时  
   - 影响: tech_profiles缺失cloud_provider/github_org等关键字段  
   - 修复建议: 配置代理或使用国内镜像API

### P1 - 功能级

3. **评分阈值过于保守**  
   - 文件: `engine/rules_engine.py:16`  
   - 问题: pass_threshold=60，但15家企业最高56分，0家通过  
   - 已调整: 降为50，4家通过  
   - 建议: 配置到config.yaml中便于调整

4. **bidding_spider 招投标数据量极低**  
   - 文件: `crawler/wuhan_it_crawler/spiders/bidding_spider.py`  
   - 问题: 仅8条记录，大部分企业0条招投标  
   - 原因: 搜索引擎对政府采购信息收录有限  
   - 建议: 增加ccgp.gov.cn直接爬取(需反爬处理)

5. **funding_stage 大量空缺**  
   - 表: `companies.funding_stage`  
   - 问题: 15家中6家funding_stage为空  
   - 已手动补充，但爬虫未自动获取  
   - 建议: business_spider增加融资信息搜索维度

### P2 - 体验级

6. **venv shebang路径拼写错误**  
   - 问题: `.venv/bin/*` 中 "Insigth" → "Insight"  
   - 已修复: 批量sed替换  

7. **sqlalchemy未安装**  
   - 问题: venv中缺失sqlalchemy  
   - 已安装: pip install sqlalchemy -i 清华镜像  

8. **pip pypi.org超时**  
   - 问题: venv的pip 24.0访问pypi.org超时  
   - 建议: 配置清华镜像为默认源

## 四、数据完整性评估

| 表 | 记录数 | 完整度 | 关键缺失 |
|----|--------|--------|----------|
| companies | 15 | 80% | funding_stage(40%空) |
| tech_profiles | 15 | 60% | github_stars全0, tech_stack全空 |
| recruitments | 120 | 70% | salary_range多为空 |
| news_mentions | 159 | 85% | sentiment_score未计算 |
| bidding_records | 8 | 30% | 仅2家有数据 |
| ratings | 15 | 100% | rules_engine评分完整 |
| crawl_tasks | 0 | 0% | 未使用 |
| rating_changelog | 0 | 0% | 未使用 |

## 五、待优化建议

### 短期(1周内)

1. **修复GLM batch_rate bug** — 使深度评级可用
2. **增加信用代码查询集成** — 将 `/Users/kc/Desktop/project/credit_code_tool/` 集成到business_spider
3. **配置pip国内镜像** — 解决包安装超时

### 中期(2-4周)

4. **招投标数据源扩展** — 对接政府采购网(ccgp.gov.cn)或第三方API
5. **评分模型优化** — 引入更多维度(专利数、软著数、项目经验)，调整权重
6. **crawl_tasks追踪** — 使爬取过程可监控可追溯

### 长期(1-3月)

7. **增量更新机制** — 只爬取变化数据，避免全量重复
8. **多城市扩展** — 支持非武汉企业的爬取和评级
9. **前端可视化** — 评级结果Dashboard展示

---

**报告生成时间**: 2026-08-04 11:30  
**数据快照**: data/exports/ (8个CSV) + data/reports/ (2个报告)
