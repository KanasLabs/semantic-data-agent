from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


_SEMANTIC_ROOTS = (
    "models",
    "rules",
    "knowledge/rules",
    "knowledge/sql",
)
_SEMANTIC_FILES = ("wren_project.yml", "relationships.yml", "relationships.yaml")


def runtime_identity() -> dict[str, str]:
    return {
        "runtime_name": "data_subagent",
        "runtime_version": "trace-v2",
        "entrypoint": "ask_data_question",
    }


def context_identity(wren: object) -> dict[str, Any]:
    project_dir = getattr(wren, "project_dir", None)
    if not isinstance(project_dir, Path):
        return _empty_context_identity()
    resolved = project_dir.resolve()
    return {
        "context_id": resolved.name,
        "candidate_id": None,
        "context_version": None,
        "publication_id": None,
        "wren_project_fingerprint": fingerprint_wren_project(resolved),
    }


def llm_identity(llm: object) -> dict[str, Any]:
    class_name = type(llm).__name__
    provider = "deepseek" if class_name == "DeepSeekLLMAdapter" else class_name
    is_deepseek = provider == "deepseek"
    return {
        "provider": provider,
        "model": getattr(llm, "model", None),
        "sql_prompt_version": "sql-v1" if is_deepseek else None,
        "repair_prompt_version": "repair-v1" if is_deepseek else None,
        "summary_prompt_version": "summary-v1" if is_deepseek else None,
    }


def empty_eval_identity() -> dict[str, None]:
    return {"run_id": None, "eval_id": None, "suite_name": None}


def empty_timings() -> dict[str, None]:
    return {
        "context": None,
        "generate_sql": None,
        "dry_plan": None,
        "dry_run": None,
        "execute": None,
        "summarize": None,
        "total": None,
    }


def initial_data_identity(query_started_at: str) -> dict[str, Any]:
    return {
        "datasource_id": None,
        "schema_fingerprint": None,
        "query_started_at": query_started_at,
        "result_sha256": None,
        "snapshot_id": None,
    }


def fingerprint_wren_project(project_dir: Path) -> str | None:
    if not project_dir.is_dir():
        return None
    paths: list[Path] = []
    for relative_name in _SEMANTIC_FILES:
        path = project_dir / relative_name
        if path.is_file() and not path.is_symlink():
            paths.append(path)
    for relative_root in _SEMANTIC_ROOTS:
        root = project_dir / relative_root
        if not root.is_dir():
            continue
        paths.extend(
            path
            for path in root.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and "__pycache__" not in path.parts
            and path.suffix.lower() != ".pyc"
        )
    if not paths:
        return None
    digest = hashlib.sha256()
    for path in sorted(set(paths), key=lambda item: item.relative_to(project_dir).as_posix()):
        relative = path.relative_to(project_dir).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _empty_context_identity() -> dict[str, None]:
    return {
        "context_id": None,
        "candidate_id": None,
        "context_version": None,
        "publication_id": None,
        "wren_project_fingerprint": None,
    }
