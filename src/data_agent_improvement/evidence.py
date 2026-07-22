from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator


def resolve_evidence_path(
    path: Path,
    project_root: Path,
    *,
    require_exists: bool = True,
) -> Path:
    root = project_root.resolve()
    resolved = (root / path).resolve() if not path.is_absolute() else path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Evidence path must remain inside project root: {resolved}") from exc
    if require_exists and not resolved.is_file():
        raise FileNotFoundError(f"Evidence file not found: {resolved}")
    return resolved


def project_relative_path(path: Path, project_root: Path) -> str:
    return path.resolve().relative_to(project_root.resolve()).as_posix()


def read_jsonl_objects(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as file:
        for line_number, raw_line in enumerate(file, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                loaded = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(loaded, dict):
                raise ValueError(f"Expected JSON object at {path}:{line_number}")
            yield line_number, loaded


def load_trace_by_id(path: Path, trace_id: str) -> dict[str, Any] | None:
    for _, record in read_jsonl_objects(path):
        if record.get("trace_id") == trace_id:
            return record
    return None
