#!/usr/bin/env bash
# ============================================================
# 一键建库脚本 — 建库 + 建表 + 灌种子数据 + 验收统计
#
# 用法: bash scripts/init_db.sh [选项]
#
#   --url URL     指定数据库连接串 (优先级最高)
#   --db  NAME    目标库名 (默认取 .env 的 DATABASE_URL, 否则 rating_system)
#   --real        使用真实企业种子 db/seed_real.sql   (默认)
#   --demo        使用演示种子   db/seed.sql          (10 家虚构企业)
#   --no-seed     只建库建表, 不灌种子数据
#   --drop        先 DROP 再重建 (危险: 清空目标库全部数据)
#   --force       目标库已有表结构时仍重新执行 init.sql (会因表已存在而报错)
#   -h, --help    显示本帮助
#
# 特性:
#   * 幂等 — 可重复执行; 已有表结构自动跳过 init.sql, 种子数据按业务唯一键去重
#   * 两种种子可任意组合/重复执行, 结果均正确 (子表按 credit_code 关联企业)
#   * 结束打印各表行数作为验收
#
# 示例:
#   bash scripts/init_db.sh
#   bash scripts/init_db.sh --demo
#   bash scripts/init_db.sh --drop
#   bash scripts/init_db.sh --url postgresql://henry@localhost:5432/scratch_db
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_DIR="$ROOT/db"

USE_DEMO=0
DO_SEED=1
DO_DROP=0
FORCE=0
DB_NAME=""
URL=""

usage() { sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --url)      URL="${2:-}"; shift 2 ;;
        --db)       DB_NAME="${2:-}"; shift 2 ;;
        --demo)     USE_DEMO=1; shift ;;
        --real)     USE_DEMO=0; shift ;;
        --no-seed)  DO_SEED=0; shift ;;
        --drop)     DO_DROP=1; shift ;;
        --force)    FORCE=1; shift ;;
        -h|--help)  usage; exit 0 ;;
        *) echo "未知参数: $1" >&2; usage; exit 2 ;;
    esac
done

# ---------- 1. 定位 psql ----------
if ! command -v psql >/dev/null 2>&1; then
    echo "❌ 找不到 psql。请先安装并启动 PostgreSQL:" >&2
    echo "     brew install postgresql@18 && brew services start postgresql@18" >&2
    exit 1
fi

# ---------- 2. 解析连接串 ----------
if [[ -z "$URL" && -f "$ROOT/.env" ]]; then
    URL="$(grep -E '^[[:space:]]*DATABASE_URL=' "$ROOT/.env" | tail -1 | cut -d= -f2- | tr -d '"'"'"'' | xargs || true)"
    [[ -n "$URL" ]] && echo "ℹ️  从 .env 读取 DATABASE_URL"
fi
[[ -z "$URL" ]] && URL="postgresql://$(whoami)@localhost:5432/rating_system"

URL_NOQ="${URL%%\?*}"                       # 去掉查询串
FROM_URL_DB="${URL_NOQ##*/}"                # 取最后一个 / 之后
[[ -n "$DB_NAME" ]] || DB_NAME="$FROM_URL_DB"
[[ -n "$DB_NAME" ]] || DB_NAME="rating_system"

if [[ ! "$DB_NAME" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    echo "❌ 库名不合法: $DB_NAME" >&2; exit 1
fi

URL="${URL_NOQ%/*}/$DB_NAME"                # 规整为目标库连接串
MAINT_URL="${URL_NOQ%/*}/postgres"          # 维护库 (建/删库用)
MASKED="$(printf '%s' "$URL" | sed -E 's#(//[^:/@]*):[^@]*@#\1:***@#')"

echo "════════════════════════════════════════════"
echo " 目标库 : $DB_NAME"
echo " 连接串 : $MASKED"
echo " 种子   : $( ((USE_DEMO)) && echo 'seed.sql (演示)' || ((DO_SEED)) && echo 'seed_real.sql (真实企业)' || echo '不灌种子' )"
echo "════════════════════════════════════════════"

# ---------- 3. 连通性 ----------
if ! psql "$MAINT_URL" -tAc 'SELECT 1' >/dev/null 2>&1; then
    echo "❌ 无法连接 PostgreSQL ($MAINT_URL)。请确认服务已启动:" >&2
    echo "     brew services start postgresql@18" >&2
    exit 1
fi

# ---------- 4. 删库 / 建库 ----------
if (( DO_DROP )); then
    echo "⚠️  --drop: 删除已有库 $DB_NAME"
    psql "$MAINT_URL" -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"$DB_NAME\" WITH (FORCE)"
fi

if [[ "$(psql "$MAINT_URL" -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'")" == "1" ]]; then
    echo "ℹ️  数据库 $DB_NAME 已存在, 复用"
else
    psql "$MAINT_URL" -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"$DB_NAME\""
    echo "✅ 已创建数据库 $DB_NAME"
fi

# ---------- 5. 建表 ----------
LOG="$(mktemp -t initdb.XXXXXX)"
trap 'rm -f "$LOG"' EXIT

run_sql_file() {                            # $1=文件路径  $2=说明
    local f="$1" desc="$2"
    if ! psql "$URL" -v ON_ERROR_STOP=1 -f "$f" >"$LOG" 2>&1; then
        echo "❌ $desc 执行失败 — 详情:" >&2
        cat "$LOG" >&2
        exit 1
    fi
    local n
    n="$(grep -cE '^(INSERT|CREATE|ALTER)' "$LOG" || true)"
    echo "✅ $desc 成功 (执行 $n 条 DDL/DML)"
    grep -E '^INSERT 0 [0-9]+' "$LOG" | awk '{s+=$3} END {if ($0!="" || s>0) printf "   写入 %d 行\n", s}' || true
}

if [[ "$(psql "$URL" -tAc "SELECT to_regclass('public.companies') IS NOT NULL")" == "t" ]]; then
    if (( FORCE )); then
        run_sql_file "$DB_DIR/init.sql" "建表 db/init.sql (--force)"
    else
        echo "ℹ️  表结构已存在, 跳过 db/init.sql (需重建请加 --drop)"
    fi
else
    run_sql_file "$DB_DIR/init.sql" "建表 db/init.sql"
fi

# ---------- 6. 种子数据 ----------
if (( DO_SEED )); then
    if (( USE_DEMO )); then
        run_sql_file "$DB_DIR/seed.sql" "种子 db/seed.sql (演示)"
    else
        run_sql_file "$DB_DIR/seed_real.sql" "种子 db/seed_real.sql (真实企业)"
    fi
else
    echo "ℹ️  --no-seed: 跳过种子数据"
fi

# ---------- 7. 验收 ----------
echo "════════════════════════════════════════════"
echo " 验收: 各表行数"
echo "────────────────────────────────────────────"
for t in companies tech_profiles recruitments news_mentions bidding_records ratings crawl_tasks rating_changelog; do
    printf " %-18s " "$t"
    psql "$URL" -tAc "SELECT count(*) FROM $t" 2>/dev/null | tr -d ' \n'
    echo
done
echo "════════════════════════════════════════════"
echo "✅ 完成。请确认 .env 的 DATABASE_URL 指向: $MASKED"
