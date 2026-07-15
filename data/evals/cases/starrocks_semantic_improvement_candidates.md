# StarRocks Semantic Improvement Candidates

This suite is separate from `starrocks_mvp_smoke.jsonl`. The smoke suite checks
basic runtime behavior; this suite checks the agreed business semantics.

## Realized Revenue Policy And Currency

Agreed business truth:

```text
total_amount is denominated in CNY
only completed orders count as realized revenue
shipped and cancelled orders do not count
```

For the deterministic local fixture, completed-only realized revenue is:

```text
120.50 + 89.00 + 56.80 + 310.20 + 145.30 = 721.80 CNY
```

Historical runs returned `1131.70` because the old contract excluded only
cancelled orders and incorrectly included shipped orders. That old SQL is not a
valid acceptance target for the conversational revision workflow.

Acceptance criteria:

- Gold SQL filters `status = 'completed'`.
- The result contains `721.80`.
- The answer includes `CNY`.
- The answer does not include `$`.
- Existing non-conflicting smoke and regression cases still pass.

Run the suite:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONIOENCODING='utf-8'
.\.venv-wren\python.exe -m data_subagent.cli eval `
  --suite data\evals\cases\starrocks_semantic_improvement_candidates.jsonl `
  --suite-name starrocks_semantic_improvement `
  --wren-project-dir data\wren\starrocks_mvp_wren_project `
  --wren-home data\wren\home `
  --limit 1
```

The Context Builder acceptance scenario must start from a baseline that does
not already encode the currency or realized-revenue policy, then demonstrate
that natural-language feedback produces this result.
