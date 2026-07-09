# Data Subagent Real ReAct Repair Demo

Date: 2026-07-08

This note records a real repair-loop demo using WrenAI CLI, DeepSeek, and the
jaffle_shop DuckDB data source.

## Purpose

The normal successful demo proves the end-to-end path, but it does not show the
repair part of the controlled ReAct loop because the first SQL succeeds.

This demo intentionally injects a bad first SQL attempt, then lets the real Wren
error flow into DeepSeek `repair_sql`, and finally executes the repaired SQL
through Wren.

## Command

```powershell
$env:PYTHONPATH='src'; .\.venv-wren\python.exe -m data_subagent.cli ask "How many orders are there?" --inject-initial-sql "SELECT bad_column FROM orders" --limit 5
```

`--inject-initial-sql` is a debug/eval-only argument. It does not change the
normal user path, where DeepSeek generates the first SQL attempt.

## Result

```json
{
  "status": "success",
  "answer": "There are 99 orders.",
  "sql": "SELECT COUNT(*) FROM orders",
  "rows": [
    {
      "count_star()": 99
    }
  ],
  "trace_id": "trace_8123219a172d4ed2b7c977e8af45a4d1",
  "warnings": [
    "debug_initial_sql was injected; first SQL attempt did not come from the LLM."
  ],
  "error": null
}
```

## ReAct Breakdown

### Action: Inject Initial SQL

```sql
SELECT bad_column FROM orders
```

This is a read-only SQL statement, so the local SQL guardrail accepts it. It is
intentionally semantically wrong because `bad_column` does not exist.

### Observation: Wren dry-plan

Wren can still compile the model reference `orders` into its expanded query
shape:

```sql
WITH orders AS (...)
SELECT bad_column FROM orders
```

### Observation: Wren dry-run Error

```text
Binder Error: Referenced column "bad_column" not found in FROM clause!
phase=SQL_DRY_RUN
```

This is the real Wren/database error that gets passed into `repair_sql`.

### Action: DeepSeek repair_sql

DeepSeek receives:

- original user question
- Wren semantic context
- confirmed examples
- failed SQL
- Wren dry-run error feedback

It returns:

```sql
SELECT COUNT(*) FROM orders
```

### Observation: Wren dry-run OK

```text
OK
```

### Action: Wren execute

```json
[
  {
    "count_star()": 99
  }
]
```

### Action: DeepSeek summarize_result

```text
There are 99 orders.
```

## Trace

Trace path:

```text
data/traces/data_subagent.jsonl
```

Trace id:

```text
trace_8123219a172d4ed2b7c977e8af45a4d1
```

Key trace fields:

```json
{
  "sql_attempts": [
    {
      "step": "inject_initial_sql",
      "sql": "SELECT bad_column FROM orders",
      "error_feedback": null
    },
    {
      "step": "repair_sql",
      "sql": "SELECT COUNT(*) FROM orders",
      "error_feedback": "Binder Error: Referenced column \"bad_column\" not found..."
    }
  ],
  "dry_run_results": [
    {
      "ok": false,
      "message": "Binder Error: Referenced column \"bad_column\" not found..."
    },
    {
      "ok": true,
      "message": "OK"
    }
  ],
  "final_sql": "SELECT COUNT(*) FROM orders",
  "status": "success"
}
```

## Interpretation

This demo shows the real controlled ReAct loop:

```text
Action: first SQL attempt
Observation: Wren dry-run error
Action: DeepSeek repair_sql
Observation: Wren dry-run OK
Action: Wren execute
Observation: rows
Action: DeepSeek summarize_result
```

The only artificial part is the first SQL attempt, which is deliberately
injected to force the repair branch. The repair itself, Wren validation, Wren
execution, and result summarization are real.
