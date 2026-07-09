# WrenAI Jaffle Shop Setup And Smoke Test

日期：2026-07-08

## 1. 本机环境决策

- WrenAI 使用项目内隔离环境：`.venv-wren`
- Python：3.11.15
- WrenAI：0.12.0
- dbt-core：1.11.12
- dbt-duckdb：1.10.1
- DuckDB：1.5.4
- Wren home：`data/wren/home`
- Wren project：`data/wren/jaffle_wren_project`
- Demo dbt project：`data/wren/jaffle_shop_duckdb`
- Trace：`data/traces/data_subagent.jsonl`
- LLM：DeepSeek `deepseek-v4-flash`

说明：官方 DeepSeek 文档显示 `deepseek-chat` / `deepseek-reasoner` 将在 2026-07-24 废弃，因此第一版直接使用 `deepseek-v4-flash`。

## 2. 已执行安装

当前机器系统 Python 是 3.9.7，不满足 WrenAI quickstart 的 Python 3.11+ 要求。因此创建了项目内 conda 环境：

```powershell
conda create -y -p .\.venv-wren python=3.11 pip
```

安装 WrenAI：

```powershell
.\.venv-wren\python.exe -m pip install "wrenai[memory,main]"
```

安装 dbt 最小依赖：

```powershell
.\.venv-wren\python.exe -m pip install "dbt-core>=1.11" "dbt-duckdb>=1.10"
```

没有直接安装 jaffle repo 的 `requirements.txt`，因为它锁定 `duckdb==1.4.4`，会与 WrenAI 的 `duckdb>=1.5.0` 产生冲突。

## 3. Jaffle Shop 数据库

拉取示例：

```powershell
git clone https://github.com/dbt-labs/jaffle_shop_duckdb.git data\wren\jaffle_shop_duckdb
```

构建 DuckDB：

```powershell
cd data\wren\jaffle_shop_duckdb
..\..\..\.venv-wren\Scripts\dbt.exe debug
..\..\..\.venv-wren\Scripts\dbt.exe build
..\..\..\.venv-wren\Scripts\dbt.exe docs generate
```

验证结果：

- `dbt debug` passed
- `dbt build` passed: 28 total, 28 pass
- `catalog.json` generated

## 4. Wren Project

项目内 Wren home：

```powershell
$env:WREN_HOME=(Resolve-Path 'data\wren\home').Path
```

从 dbt profile 导入 Wren profile：

```powershell
.\.venv-wren\Scripts\wren.exe profile import dbt `
  --project-dir data\wren\jaffle_shop_duckdb `
  --profiles-path data\wren\jaffle_shop_duckdb\profiles.yml `
  --profile jaffle_shop `
  --target dev `
  --name jaffle_shop `
  --activate
```

初始化 Wren project：

```powershell
.\.venv-wren\Scripts\wren.exe context init `
  -p data\wren\jaffle_wren_project `
  --empty `
  --force
```

从 dbt import context：

```powershell
.\.venv-wren\Scripts\wren.exe context import dbt `
  -p data\wren\jaffle_wren_project `
  --project-dir data\wren\jaffle_shop_duckdb `
  --profiles-path data\wren\jaffle_shop_duckdb\profiles.yml `
  --profile jaffle_shop `
  --target dev `
  --force
```

绑定 profile 时，Windows GBK 控制台会因为 Wren 输出 `✓` 字符报 `UnicodeEncodeError`。解决方式是在命令中设置：

```powershell
$env:PYTHONIOENCODING='utf-8'
```

最终 validate/build：

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:WREN_HOME=(Resolve-Path 'data\wren\home').Path
.\.venv-wren\Scripts\wren.exe context validate -p data\wren\jaffle_wren_project
.\.venv-wren\Scripts\wren.exe context build -p data\wren\jaffle_wren_project
```

验证结果：

- `context validate`：0 errors, 3 warnings
- warning 是 staging models 缺 description，不阻塞 MVP
- `context build`：5 models, 0 views, generated `target/mdl.json`

## 5. Wren CLI 行为记录

可稳定使用：

```powershell
wren memory describe
wren context show --output json
wren dry-plan --sql "select count(*) as order_count from orders"
wren dry-run --sql "select count(*) as order_count from orders"
wren query --sql "select count(*) as order_count from orders" --output json --quiet
```

实际 smoke test：

```json
{"order_count":99}
```

注意：

- `dry-plan` 没有 JSON 输出，返回 expanded SQL 文本。
- `dry-run` 没有 JSON 输出，成功返回 `OK`，失败返回错误文本。
- `query --output json` 返回 JSON object 行，不一定是 JSON array。
- `memory fetch` / `memory recall` 在 Windows 首次运行会进入 memory/embedding 初始化，实测会长时间卡住。第一版 adapter 暂不依赖它们。

第一版 adapter 策略：

- `get_context` 使用 `context show --output json` + `memory describe`
- `recall_examples` 直接读取 `knowledge/sql/*.md` confirmed NL-SQL examples
- `dry_plan` / `dry_run` / `query` 走 Wren CLI

## 6. Data Subagent Smoke Test

单测：

```powershell
$env:PYTHONPATH='src'
.\.venv-wren\python.exe -m unittest discover -s tests
```

结果：

```text
Ran 7 tests
OK
```

Wren doctor：

```powershell
$env:PYTHONPATH='src'
.\.venv-wren\python.exe -m data_subagent.cli doctor-wren
```

结果：

```json
{
  "models": ["customers", "orders", "stg_customers", "stg_orders", "stg_payments"],
  "dry_run_ok": true,
  "dry_run_message": "OK"
}
```

真实 DeepSeek + Wren 问数：

```powershell
$env:PYTHONPATH='src'
.\.venv-wren\python.exe -m data_subagent.cli ask "How many orders are there?"
```

结果摘要：

```json
{
  "status": "success",
  "sql": "SELECT COUNT(*) FROM orders",
  "rows": [{"count_star()": 99}],
  "error": null
}
```

第二个问题：

```powershell
.\.venv-wren\python.exe -m data_subagent.cli ask "Show the top 5 customers by customer lifetime value" --limit 5
```

结果摘要：

```json
{
  "status": "success",
  "sql": "SELECT customer_id, first_name, last_name, customer_lifetime_value FROM customers ORDER BY customer_lifetime_value DESC LIMIT 5",
  "rows": [
    {"customer_id": 51, "first_name": "Howard", "last_name": "R.", "customer_lifetime_value": 99.0}
  ],
  "chart_spec": {"mark": "bar"}
}
```

## 7. 当前限制

- 第一版使用 Wren CLI adapter，尚未切换 Wren Python SDK。
- `memory fetch` / `memory recall` 暂不进入主链路。
- DeepSeek 输出 summary 的 `confidence` 可能是 `high/medium/low`，代码已做映射。
- Wren profile 内有本机绝对路径，因此 `data/wren/home` 不应提交。
- jaffle dbt clone 和 DuckDB 数据库不应提交，应通过文档或脚本重建。
