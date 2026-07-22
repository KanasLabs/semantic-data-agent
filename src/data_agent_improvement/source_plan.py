from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceEvaluationCommand:
    name: str
    args: list[str]
    timeout_seconds: int = 900
    environment: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Source evaluation command name must not be empty.")
        if not self.args or any(not str(arg).strip() for arg in self.args):
            raise ValueError("Source evaluation command args must not be empty.")
        if self.timeout_seconds < 1:
            raise ValueError("Source evaluation command timeout must be positive.")
        forbidden_names = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
        if any(
            any(marker in name.upper() for marker in forbidden_names)
            for name in self.environment
        ):
            raise ValueError("Source evaluation commands cannot receive credential variables.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "args": list(self.args),
            "timeout_seconds": self.timeout_seconds,
            "environment": dict(self.environment),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceEvaluationCommand":
        args = data.get("args")
        if not isinstance(args, list):
            raise ValueError("Source evaluation command args must be a JSON array.")
        environment = data.get("environment") or {}
        if not isinstance(environment, dict):
            raise ValueError("Source evaluation command environment must be an object.")
        return cls(
            name=str(data["name"]),
            args=[str(arg) for arg in args],
            timeout_seconds=int(data.get("timeout_seconds", 900)),
            environment={
                str(name): str(value)
                for name, value in environment.items()
            },
        )


def source_evaluation_plan(
    commands: list[SourceEvaluationCommand],
) -> dict[str, Any]:
    if not commands:
        raise ValueError("SI3 requires at least one frozen evaluation command.")
    names = [command.name for command in commands]
    if len(names) != len(set(names)):
        raise ValueError("Source evaluation command names must be unique.")
    return {
        "schema_version": 1,
        "commands": [command.to_dict() for command in commands],
    }


def source_evaluation_plan_sha256(plan: dict[str, Any]) -> str:
    payload = json.dumps(
        plan,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def load_source_evaluation_plan(
    *,
    path: Path,
    expected_sha256: str,
) -> list[SourceEvaluationCommand]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Source evaluation plan is unavailable or invalid: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Source evaluation plan schema is invalid.")
    if source_evaluation_plan_sha256(payload) != expected_sha256:
        raise ValueError("Source evaluation plan hash changed after Job preparation.")
    commands = payload.get("commands")
    if not isinstance(commands, list) or not all(isinstance(item, dict) for item in commands):
        raise ValueError("Source evaluation plan commands are invalid.")
    parsed = [SourceEvaluationCommand.from_dict(item) for item in commands]
    source_evaluation_plan(parsed)
    return parsed
