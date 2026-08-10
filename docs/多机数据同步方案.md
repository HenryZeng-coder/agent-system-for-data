# 多机数据同步方案 — 武汉IT企业智能评级系统

> 目标: 不同电脑爬取数据及时同步，避免重复和错漏
> 日期: 2026-08-06

---

## 一、现状盘点（关键约束）

### 1.1 数据库连接方式
所有模块均通过 `DATABASE_URL` 环境变量连接 PostgreSQL（`crawler/settings.py`、
`engine/*.py`、`scripts/*.py`），默认 `postgresql://kc@localhost:5432/rating_system`。
→ **切换集中式数据库 = 各机改 .env 一行配置，代码几乎不动。**

### 1.2 去重/幂等能力现状

| 表 | 唯一约束 | 写入方式 | 多机并发风险 |
|----|---------|---------|------------|
| companies | UNIQUE(credit_code) ✓ | ON CONFLICT DO UPDATE ✓ | 低 |
| tech_profiles | 无 (缺 UNIQUE(company_id)) | ON CONFLICT (company_id) — **无约束支撑会报错** | 中(隐患) |
| recruitments | 无 | 普通 INSERT | 高(重复) |
| news_mentions | 无 | 普通 INSERT | 高(重复) |
| bidding_records | 无 | 普通 INSERT | 高(重复) |
| crawl_tasks | 无 | 普通 INSERT | 中(任务重复) |
| ratings | UNIQUE(company_id, rated_by) ✓ | ON CONFLICT DO UPDATE ✓ | 低 |

**结论: 单机去重靠 DedupPipeline 内存 set（进程内有效）；多机/跨进程时
recruitments/news_mentions/bidding_records 会重复插入。这是"重复"问题的根源。**

### 1.3 错漏风险点
- tech_profiles 的 ON CONFLICT (company_id) 在无唯一约束表上执行会抛
  "no unique or exclusion constraint matching"（需补约束或该分支从未触发）
- 关联表缺 updated_at 类时间戳 → 无法判断新旧、无法做增量同步
- 无采集任务状态机 → 断网/失败后无法追踪"哪家企业漏了"

---

## 二、技术路线（4 选 1，可组合）

### 方案 A：集中式云 PostgreSQL（推荐，长期正确）

```
爬虫机1 ─┐
爬虫机2 ─┼─→ 云 PostgreSQL (腾讯云/阿里云/自建轻量主机) ←── 规则引擎/报告
爬虫机3 ─┘        实时读写, 数据库层幂等去重
```

- **同步方式**: 实时（直连），唯一约束 + ON CONFLICT 天然防重
- **改造点**:
  1. 各机 .env 的 DATABASE_URL 指向云端（含 SSL）
  2. 补 4 张表的业务唯一约束 + 写入改 ON CONFLICT（详见部署 §3.2）
  3. （可选）crawl_tasks 任务分配，避免多机爬同一企业
- **优点**: 实时、最简单、改动最小、去重彻底、现有代码全部复用
- **缺点**: 依赖公网；境外云（Supabase/Neon）国内访问慢 → 必须选国内云
- **安全**: 推荐 Tailscale/ZeroTier 组虚拟内网（各机+云主机装客户端），
  PostgreSQL 只监听虚拟内网 IP，不暴露公网端口，免费且最安全
- **成本**: 轻量云主机 2C2G 约 30-60 元/月（自装 PG16）；或云 RDS 基础版
- **工作量**: 0.5~1 天

### 方案 B：本地库 + 定时增量同步（中心-边缘）

```
爬虫机1 本地PG ──┐
爬虫机2 本地PG ──┼──(定时增量推送/拉取)──→ 中心库
爬虫机3 本地PG ──┘
```

- **同步方式**:
  - 简单版: 定时 pg_dump 全量 + 按 updated_at 增量导出导入（数据量小可用）
  - 正规版: PostgreSQL 逻辑复制（发布/订阅，单向）、Bucardo（双向）
- **优点**: 断网可继续爬、本地响应快、不依赖公网
- **缺点**: 多主写冲突（两机改同一企业互相覆盖）、同步有延迟、
  逻辑复制对 schema 变更敏感（加列需重建发布）
- **适合**: 网络不稳定、或对数据主权有要求
- **工作量**: 1~2 天（逻辑复制） / 0.5 天（dump 增量）

### 方案 C：中心采集服务（API 网关，扩展方向）

```
爬虫机1 ─┐   POST /api/items (幂等)
爬虫机2 ─┼─→ FastAPI 中心服务 → 中心库
爬虫机3 ─┘   GET /api/tasks (任务领取)
```

- 爬虫侧加 HttpPipeline 把 Item 改为 HTTP POST；中心服务负责幂等入库 +
  任务分配 + 认证限流
- **优点**: 完全解耦、可管控、任务分配天然、schema 变更不影响存量爬虫
- **缺点**: 需开发和运维中心服务
- **适合**: 机器数量多、需要外部接入或团队协作
- **工作量**: 2~3 天

### 方案 D：git + 导出文件同步（零成本过渡）

```
每台机 cron: 导出全量CSV → git push; 其他机 git pull → import
```

- 复用现有 `data/exports/*.csv`（已有 companies/ratings/tech_profiles 等导出）
- **优点**: 零成本、今天就能用、与现有 git 流程一致
- **缺点**: 非实时、两台机器同时改同一企业会覆盖、表结构变更需手工同步
- **适合**: 2 台机器、低频同步、数据量小

### 推荐组合
- **主路线: 方案 A**（集中式 + Tailscale 虚拟内网，国内轻量主机自装 PG16）
- 过渡: 今天可用方案 D 顶几天
- 未来扩展: 机器 >5 台或需外部接入时升级方案 C

---

## 三、部署方案（方案 A 详细）

> **实施状态: 2026-08-06 已完成数据库层防重复改造 (P0), 同步脚本已就绪 (方案D)**

### 3.0 已实施内容 (本次)
- ✅ 4 张表唯一约束: tech_profiles(company_id)、recruitments(company_id,
  position_title, source_name)、news_mentions(company_id, title,
  source_name)、bidding_records(company_id, project_name, source_name)
  —— 已写入 db/init.sql (新环境自动生效) 并已应用到运行库
- ✅ standardize_pipeline 三处 INSERT 改为 ON CONFLICT DO NOTHING (幂等,
  多机并发/重跑不再重复插入)
- ✅ 修复 tech_profiles 原有 ON CONFLICT (company_id) 无约束支撑的隐患
- ✅ scripts/export_sync.py — 导出6表为 CSV (爬取机执行)
- ✅ scripts/import_sync.py — 幂等导入, 跨机 id 重映射, 可重复执行
  (已验证: 导入一致性 + 幂等性 + 重复0 + pytest 166 passed)
- ✅ docs/多机数据同步方案.md — 本方案文档

### 3.0.1 方案D 使用流程 (零成本过渡, 今天可用)
```bash
# 爬取机 (采集完成后):
python scripts/export_sync.py && git add data/sync && git commit -m "sync: data" && git push

# 汇聚机 (每天/每次需要最新数据时):
git pull && python scripts/import_sync.py
# 可选: ratings 以导入文件为准: python scripts/import_sync.py --update-ratings
```
> 注意: 汇聚机与爬取机不要同时爬同一批企业 (重复浪费); 多机爬取时
> 建议各机分配不同 spider/关键词。crawl_tasks 任务分配为后续升级项。

### 3.1 基础设施
1. 腾讯云/阿里云轻量应用服务器（2C2G, Ubuntu 22.04, 约 30-60 元/月）
   - 安装: PostgreSQL 16 + Tailscale/ZeroTier
   - 或云 RDS PostgreSQL 基础版（免运维+自动备份，略贵）
2. 各爬虫机安装 Tailscale/ZeroTier，与服务器组虚拟内网
3. PostgreSQL 配置: 监听虚拟内网 IP，`pg_hba.conf` 仅放行虚拟网段，
   `ssl=on`（可自签证书），强密码
4. 初始化: `psql -h <内网IP> -f db/init.sql`（含 3.2 的约束变更）+
   `db/seed.sql`，一次导入

### 3.2 数据库改造（防重复核心）
```sql
-- 修复 tech_profiles (ON CONFLICT 支撑)
ALTER TABLE tech_profiles ADD CONSTRAINT uq_tech_profiles_company
    UNIQUE (company_id);

-- recruitments: 业务唯一键 (与 DedupPipeline 一致)
ALTER TABLE recruitments ADD CONSTRAINT uq_recruitments_key
    UNIQUE (company_id, position_title, source_name);

-- news_mentions: 标题截断 200 与去重逻辑一致 (VARCHAR 上限内)
ALTER TABLE news_mentions ADD CONSTRAINT uq_news_key
    UNIQUE (company_id, title, source_name);

-- bidding_records
ALTER TABLE bidding_records ADD CONSTRAINT uq_bidding_key
    UNIQUE (company_id, project_name, source_name);

-- crawl_tasks: 任务去重 + 分配
ALTER TABLE crawl_tasks ADD CONSTRAINT uq_crawl_task_key
    UNIQUE (spider_name, task_type, target_company_id);
```
> 注: news_mentions.title 若字段超长，需先截断或改用哈希唯一列；
> 加约束前用 `SELECT ... GROUP BY ... HAVING count(*)>1` 清理存量重复。

### 3.3 代码改造（standardize_pipeline.py）
- recruitments/news_mentions/bidding_records 的 INSERT 改
  `ON CONFLICT (...) DO UPDATE SET ...`（保留最新，或 DO NOTHING 保留首条）
- tech_profiles 已有 ON CONFLICT (company_id)，补约束后即生效
- DedupPipeline 内存去重保留（减少网络写放大），数据库约束兜底

### 3.4 防漏采集（可选, 推荐）
crawl_tasks 状态机化:
- 每台机启动时 `SELECT ... WHERE status='pending' ORDER BY id LIMIT N FOR UPDATE SKIP LOCKED`
- 领取后置 running + worker_id，完成置 done，失败置 failed 并自动重试
- 每日校验: `SELECT count(*) FROM crawl_tasks WHERE status='failed'` +
  各表最新数据时间, 汇总进 logs/ 日志

### 3.5 并发更新冲突策略
- 各表增加 `updated_at TIMESTAMP DEFAULT NOW()`（recruitments 等缺）
- 写入用 `ON CONFLICT DO UPDATE SET ... , updated_at=NOW()`，
  两机同写一企业以最后提交为准（本系统数据非强一致场景，可接受）
- ratings 已是幂等 ON CONFLICT DO UPDATE，无需改

### 3.6 备份与监控
- 备份: RDS 自动备份 / 自建 `pg_dump` cron（每日全量，保留7天）
- 监控: 每日脚本查询 crawl_tasks 状态分布 + 各表行数与最新时间，
  写入 logs/（复用现有日志体系）
- 变更: schema 变更先在 test 机验证再上中心库（沿用 test→master 流程）

### 3.7 各机配置清单
```bash
# 每台机器 .env
DATABASE_URL=postgresql://rating:<强密码>@<虚拟内网IP>:5432/rating_system?sslmode=require
DEEPSEEK_API_KEY=...        # 同一 Key 多机共用（注意 TPM 限额, 429 已有退避）
PROXY_POOL_API=...
```

---

## 四、改造工作量与优先级

| 任务 | 方案 | 工作量 | 状态 |
|------|------|--------|------|
| P0: 4张表唯一约束 + 写入幂等化 | A | 0.5 天 | ✅ 已完成 |
| P0: 各机 DATABASE_URL 切换 + 初始化中心库 | A | 0.5 天 | 待云资源确认 |
| P1: Tailscale 虚拟内网 + SSL + 备份 cron | A | 0.5 天 | 待云资源确认 |
| P1: crawl_tasks 任务分配 + 防漏校验 | A | 1 天 | 未开始 |
| P2: updated_at 时间戳 + 冲突策略 | A | 0.5 天 | 未开始 |
| 过渡: 导出/导入 cron (方案 D) | D | 0.5 天 | ✅ 脚本已就绪(未挂cron) |

## 五、风险与注意
1. **公网暴露数据库风险高** → 必须虚拟内网或白名单 + SSL + 强密码
2. 国内访问境外云（Supabase/Neon）慢且可能不稳定 → 主力选国内云
3. 加唯一约束前先清理存量重复数据
4. news_mentions.title 超长 → 约束前截断或改 hash 列
5. DeepSeek API Key 多机共用注意 TPM 限额（llm_client 已有 429 自适应退避）
6. 逻辑复制（方案B）对 schema 变更敏感，选方案B时需固定发布集合
