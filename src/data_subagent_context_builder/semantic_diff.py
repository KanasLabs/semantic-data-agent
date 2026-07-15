from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .revision_store import SemanticDiff


def generate_semantic_diff(
    *,
    revision_id: str,
    base_candidate_id: str,
    candidate_id: str,
    base_project_dir: Path,
    candidate_project_dir: Path,
    assumptions: list[str] | None = None,
    unresolved_questions: list[str] | None = None,
    test_coverage: list[dict[str, Any]] | None = None,
) -> SemanticDiff:
    base_models = _load_models(base_project_dir)
    candidate_models = _load_models(candidate_project_dir)
    model_changes: list[dict[str, Any]] = []
    field_changes: list[dict[str, Any]] = []

    for model_name in sorted(set(base_models) | set(candidate_models)):
        before = base_models.get(model_name)
        after = candidate_models.get(model_name)
        if before is None:
            model_changes.append({"model": model_name, "change": "added", "after": after})
        elif after is None:
            model_changes.append({"model": model_name, "change": "removed", "before": before})
        else:
            before_model = _without_columns(before)
            after_model = _without_columns(after)
            if not _equivalent(before_model, after_model):
                model_changes.append(
                    {
                        "model": model_name,
                        "change": "changed",
                        "before": before_model,
                        "after": after_model,
                    }
                )
        field_changes.extend(_diff_fields(model_name, before, after))

    relationship_changes = _diff_named_records(
        _load_relationships(base_project_dir),
        _load_relationships(candidate_project_dir),
        label="relationship",
    )
    rule_changes = _diff_markdown_tree(
        base_project_dir / "knowledge" / "rules",
        candidate_project_dir / "knowledge" / "rules",
    )
    sql_example_changes = _diff_markdown_tree(
        base_project_dir / "knowledge" / "sql",
        candidate_project_dir / "knowledge" / "sql",
    )
    return SemanticDiff(
        revision_id=revision_id,
        base_candidate_id=base_candidate_id,
        candidate_id=candidate_id,
        models=model_changes,
        fields=field_changes,
        relationships=relationship_changes,
        rules=rule_changes,
        sql_examples=sql_example_changes,
        assumptions=list(assumptions or []),
        unresolved_questions=list(unresolved_questions or []),
        test_coverage=list(test_coverage or []),
    )


def _load_models(project_dir: Path) -> dict[str, dict[str, Any]]:
    models: dict[str, dict[str, Any]] = {}
    for path in sorted((project_dir / "models").glob("*/metadata.yml")):
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and loaded.get("name"):
            models[str(loaded["name"])] = loaded
    return models


def _load_relationships(project_dir: Path) -> dict[str, dict[str, Any]]:
    path = project_dir / "relationships.yml"
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    relationships = loaded.get("relationships") if isinstance(loaded, dict) else loaded
    if not isinstance(relationships, list):
        return {}
    return {
        str(item["name"]): item
        for item in relationships
        if isinstance(item, dict) and item.get("name")
    }


def _without_columns(model: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in model.items() if key != "columns"}


def _diff_fields(
    model_name: str,
    before_model: dict[str, Any] | None,
    after_model: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    before_fields = _named_columns(before_model)
    after_fields = _named_columns(after_model)
    changes: list[dict[str, Any]] = []
    for field_name in sorted(set(before_fields) | set(after_fields)):
        before = before_fields.get(field_name)
        after = after_fields.get(field_name)
        if before is None:
            changes.append(
                {"model": model_name, "field": field_name, "change": "added", "after": after}
            )
        elif after is None:
            changes.append(
                {
                    "model": model_name,
                    "field": field_name,
                    "change": "removed",
                    "before": before,
                }
            )
        elif not _equivalent(before, after):
            changes.append(
                {
                    "model": model_name,
                    "field": field_name,
                    "change": "changed",
                    "before": before,
                    "after": after,
                }
            )
    return changes


def _named_columns(model: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not model:
        return {}
    columns = model.get("columns")
    if not isinstance(columns, list):
        return {}
    return {
        str(item["name"]): item
        for item in columns
        if isinstance(item, dict) and item.get("name")
    }


def _diff_named_records(
    before_records: dict[str, dict[str, Any]],
    after_records: dict[str, dict[str, Any]],
    *,
    label: str,
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for name in sorted(set(before_records) | set(after_records)):
        before = before_records.get(name)
        after = after_records.get(name)
        if before is None:
            changes.append({label: name, "change": "added", "after": after})
        elif after is None:
            changes.append({label: name, "change": "removed", "before": before})
        elif not _equivalent(before, after):
            changes.append(
                {label: name, "change": "changed", "before": before, "after": after}
            )
    return changes


def _diff_markdown_tree(before_dir: Path, after_dir: Path) -> list[dict[str, Any]]:
    before_files = _load_markdown_tree(before_dir)
    after_files = _load_markdown_tree(after_dir)
    changes: list[dict[str, Any]] = []
    for relative_path in sorted(set(before_files) | set(after_files)):
        before = before_files.get(relative_path)
        after = after_files.get(relative_path)
        if before is None:
            changes.append({"path": relative_path, "change": "added", "after": after})
        elif after is None:
            changes.append({"path": relative_path, "change": "removed", "before": before})
        elif before != after:
            changes.append(
                {"path": relative_path, "change": "changed", "before": before, "after": after}
            )
    return changes


def _load_markdown_tree(directory: Path) -> dict[str, str]:
    if not directory.exists():
        return {}
    return {
        path.relative_to(directory).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(directory.rglob("*.md"))
    }


def _equivalent(before: Any, after: Any) -> bool:
    return json.dumps(before, ensure_ascii=False, sort_keys=True) == json.dumps(
        after, ensure_ascii=False, sort_keys=True
    )
