from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml


def make_smoke_eval(
    *,
    wren_project_dir: Path,
    output_path: Path,
    dataset: str | None = None,
    db_id: str | None = None,
    max_cases: int = 3,
    include_relationship_case: bool = False,
) -> dict[str, Any]:
    wren_project_dir = wren_project_dir.resolve()
    output_path = output_path.resolve()
    models = load_models(wren_project_dir)
    if not models:
        raise ValueError(f"No Wren model metadata found under {wren_project_dir}")

    project_name = _project_name(wren_project_dir)
    suite_dataset = dataset or project_name
    suite_db_id = db_id or project_name
    cases: list[dict[str, Any]] = []
    for model in models[: max(0, max_cases)]:
        model_name = str(model["name"])
        cases.append(
            {
                "eval_id": _safe_eval_id(f"{project_name}_{model_name}_count"),
                "dataset": suite_dataset,
                "db_id": suite_db_id,
                "question": f"How many rows are in {model_name}?",
                "evidence": f"Use the Wren model `{model_name}`.",
                "expected_status": "success",
                "expected_sql_contains": ["count", model_name],
                "expected_row_count": 1,
            }
        )

    if include_relationship_case and len(cases) < max_cases:
        relationship_case = _relationship_case(
            project_name=project_name,
            dataset=suite_dataset,
            db_id=suite_db_id,
            wren_project_dir=wren_project_dir,
        )
        if relationship_case:
            cases.append(relationship_case)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        for case in cases:
            file.write(json.dumps(case, ensure_ascii=False) + "\n")

    return {
        "ok": True,
        "wren_project_dir": str(wren_project_dir),
        "output_path": str(output_path),
        "dataset": suite_dataset,
        "db_id": suite_db_id,
        "emitted": len(cases),
        "eval_ids": [case["eval_id"] for case in cases],
    }


def load_models(wren_project_dir: Path) -> list[dict[str, Any]]:
    models_dir = wren_project_dir / "models"
    if not models_dir.exists():
        return []
    models: list[dict[str, Any]] = []
    for path in sorted(models_dir.glob("*/metadata.yml")):
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and loaded.get("name"):
            models.append(loaded)
    return models


def _relationship_case(
    *,
    project_name: str,
    dataset: str,
    db_id: str,
    wren_project_dir: Path,
) -> dict[str, Any] | None:
    relationships_path = wren_project_dir / "relationships.yml"
    if not relationships_path.exists():
        return None
    loaded = yaml.safe_load(relationships_path.read_text(encoding="utf-8"))
    relationships = loaded.get("relationships") if isinstance(loaded, dict) else None
    if not isinstance(relationships, list) or not relationships:
        return None
    first = relationships[0]
    if not isinstance(first, dict):
        return None
    models = first.get("models")
    if not isinstance(models, list) or len(models) < 2:
        return None
    left = str(models[0])
    right = str(models[1])
    return {
        "eval_id": _safe_eval_id(f"{project_name}_{left}_{right}_relationship_smoke"),
        "dataset": dataset,
        "db_id": db_id,
        "question": f"How many {left} rows have related {right}?",
        "evidence": f"Use the Wren relationship `{first.get('name')}` between `{left}` and `{right}`.",
        "expected_status": "success",
        "expected_sql_contains": ["count", left, right],
        "expected_row_count": 1,
    }


def _project_name(wren_project_dir: Path) -> str:
    project_file = wren_project_dir / "wren_project.yml"
    if project_file.exists():
        loaded = yaml.safe_load(project_file.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and loaded.get("name"):
            return str(loaded["name"])
    return wren_project_dir.name


def _safe_eval_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")
    return safe or "wren_smoke"
