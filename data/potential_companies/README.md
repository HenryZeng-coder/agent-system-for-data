# 企业底池 (potential_companies)

本目录存放待评级的**候选企业名单**。流水线的起点就是这里的一个 CSV。

## 目录内文件约定

| 文件 | 说明 |
|------|------|
| `company_pool.csv` | 你的企业底池（**需自己准备**，本仓库不附带任何名单） |
| `company_pool.template.csv` | 空模板，含表头，可直接改名使用 |
| `credit_codes.csv` | `scripts/fetch_credit_codes.py` 输出的信用代码补全结果 |
| `biz_info.csv` | `scripts/fetch_biz_info.py` 输出的工商信息补全结果 |
| `biz_info_v2.csv` | `scripts/fetch_biz_info_v2.py` 的第二渠道补全结果 |
| `company_pool_scored.csv` | `scripts/incremental_crawl_and_score.py` 输出的评分结果 |

## 名单 CSV 的最小格式

只需两列，工商字段全部可以由后续脚本/爬虫补全：

```csv
company_name,source_category
某某科技有限公司,数字化转型试点
某某智能装备股份有限公司,智能工厂
```

- `company_name`：**必填**，企业工商全称（简称会导致后续查找失败）
- `source_category`：可选，来源类别，导入时作为 `industry_tags` 的近似标签

## 全国底池怎么来（免费公开渠道）

不要用大模型生成企业名单——那会引入大量不存在的公司。可用的真实来源：

1. **各省市工信/经信部门官网公示栏**：数字化转型试点、智能工厂、专精特新、
   人工智能应用服务商、工业互联网平台等认定名单，均为免费公开数据。
   检索思路：`<省/市>工业和信息化厅 公示 认定 名单`。
2. **国家级名单**：工信部「中小企业数字化转型试点城市」「智能制造示范工厂」
   「专精特新小巨人」等公示名单，可一次覆盖多个省份。
3. **公共资源交易/政府采购平台**：中标公告里的供应商名称，天然带数字化项目线索。
4. **企业信息公示系统**（国家企业信用信息公示系统）：用于核验名称与信用代码。

拿到附件（docx/xls/pdf）后解析出企业名，规范化去重，导出成上面的两列 CSV 即可。

## 导入数据库

```bash
# 只导入名单（工商字段留空, 后续由爬虫/补全脚本填充）
python scripts/import_company_pool.py --csv data/potential_companies/company_pool.csv

# 或带工商字段时直接导入
python scripts/import_csv_to_db.py --csv data/potential_companies/company_pool.csv
```

导入后 `companies.status = 'raw'`，等待被爬取与评分。
