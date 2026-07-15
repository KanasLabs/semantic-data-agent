from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .starrocks_onboarding import build_starrocks_query_command


@dataclass(frozen=True)
class StarRocksRevisionConfig:
    host: str
    port: int
    database: str
    user: str
    password_env: str = "CONTEXT_BUILDER_STARROCKS_PASSWORD"
    allow_empty_password: bool = False
    allowed_catalogs: tuple[str, ...] = ("default_catalog",)
    allowed_databases: tuple[str, ...] = ()
    max_query_rows: int = 100
    query_timeout_seconds: int = 15


@dataclass(frozen=True)
class PreparedStarRocksRevisionAccess:
    config: StarRocksRevisionConfig
    query_command: str
    evidence_path: Path
    access_record_path: Path


def prepare_starrocks_revision_access(
    *,
    config: StarRocksRevisionConfig,
    project_root: Path,
    candidate_project_dir: Path,
    artifact_root: Path,
    require_credentials: bool,
) -> PreparedStarRocksRevisionAccess:
    allowed_databases = config.allowed_databases or (config.database,)
    if not config.host.strip() or not config.database.strip() or not config.user.strip():
        raise ValueError("StarRocks revision access requires host, database, and user.")
    if config.port < 1 or config.max_query_rows < 1 or config.query_timeout_seconds < 1:
        raise ValueError("StarRocks revision access limits and port must be positive.")
    if not config.allowed_catalogs:
        raise ValueError("StarRocks revision access requires an allowed catalog.")
    if config.database.lower() not in {item.lower() for item in allowed_databases}:
        raise ValueError("Active StarRocks database must be in the database allowlist.")
    if require_credentials and not config.allow_empty_password and not os.environ.get(
        config.password_env
    ):
        raise RuntimeError(
            f"Required StarRocks password environment variable is not set: {config.password_env}"
        )
    evidence_path = (
        candidate_project_dir.resolve() / "onboarding" / "revision_query_evidence.jsonl"
    )
    query_command = build_starrocks_query_command(
        project_root=project_root.resolve(),
        host=config.host,
        port=config.port,
        database=config.database,
        user=config.user,
        password_env=config.password_env,
        allow_empty_password=config.allow_empty_password,
        allowed_catalogs=config.allowed_catalogs,
        allowed_databases=allowed_databases,
        max_query_rows=config.max_query_rows,
        query_timeout_seconds=config.query_timeout_seconds,
        evidence_path=evidence_path,
    )
    access_record_path = artifact_root.resolve() / "starrocks_access.json"
    access_record_path.parent.mkdir(parents=True, exist_ok=True)
    access_record = {
        **asdict(config),
        "allowed_databases": list(allowed_databases),
        "password_env": config.password_env,
        "password_value_persisted": False,
        "evidence_path": str(evidence_path),
    }
    access_record_path.write_text(
        json.dumps(access_record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return PreparedStarRocksRevisionAccess(
        config=config,
        query_command=query_command,
        evidence_path=evidence_path,
        access_record_path=access_record_path,
    )


def validate_revision_query_evidence(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "args": ["validate-revision-query-evidence", str(path)],
            "returncode": 0,
            "stdout": "Controlled StarRocks access was authorized but not used.",
            "stderr": "",
            "executed_queries": 0,
            "status": "not_used",
        }
    errors: list[str] = []
    executed_queries = 0
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            loaded = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid evidence line {line_number}: {exc}")
            continue
        if not isinstance(loaded, dict):
            errors.append(f"Evidence line {line_number} must be a JSON object.")
            continue
        if "rows" in loaded:
            errors.append(f"Evidence line {line_number} unexpectedly contains result rows.")
        if loaded.get("status") == "executed":
            executed_queries += 1
    if executed_queries == 0:
        errors.append("Query evidence exists but contains no executed query.")
    return {
        "args": ["validate-revision-query-evidence", str(path)],
        "returncode": 1 if errors else 0,
        "stdout": f"Valid revision evidence with {executed_queries} executed queries."
        if not errors
        else "",
        "stderr": "\n".join(errors),
        "executed_queries": executed_queries,
        "status": "used" if executed_queries else "invalid",
    }


def archive_revision_query_evidence(
    access: PreparedStarRocksRevisionAccess,
    artifact_root: Path,
) -> Path | None:
    if not access.evidence_path.exists():
        return None
    archive_path = artifact_root.resolve() / "starrocks_query_evidence.jsonl"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(access.evidence_path, archive_path)
    return archive_path
