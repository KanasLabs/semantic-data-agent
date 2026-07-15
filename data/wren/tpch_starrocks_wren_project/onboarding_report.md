# Wren Context Builder Onboarding Report

Generated at: 2026-07-14T05:08:28.055643+00:00

## Summary

- Status: OK
- Project name: `tpch_starrocks`
- Source: `existing_wren_project`
- Wren project: `<project-root>\data\wren\tpch_starrocks_wren_project`
- Wren home: `<project-root>\data\wren\home`
- Models: 8
- Relationships: 8

## Models

- `customer`
- `lineitem`
- `nation`
- `orders`
- `part`
- `partsupp`
- `region`
- `supplier`

## Wren Commands

### context_validate

```text
args: context validate
returncode: 0
stdout:
Valid — 8 models, 0 views, 8 relationships.
stderr:

```

### context_build

```text
args: context build
returncode: 0
stdout:
Built: 8 models, 0 views → <project-root>\data\wren\tpch_starrocks_wren_project\target\mdl.json

Next: wren --sql 'SELECT ...' to query your data.
stderr:

```

### dry_run

```text
args: dry-run --sql SELECT COUNT(*) AS order_count FROM orders
returncode: 0
stdout:
OK
stderr:

```

## Codex Execution

No Codex execution data.

## Limitations

- Automatically generated schema-level MDL is a draft semantic layer.
- Business metrics, synonyms, field definitions, permissions, and time semantics need human or business-document input.
- Relationships come from database metadata and should be reviewed before relying on relationship-driven joins.
