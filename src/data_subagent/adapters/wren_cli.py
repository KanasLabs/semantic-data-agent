from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from data_subagent.adapters.wren_base import WrenAdapter
from data_subagent.models import DryRunResult, ExecuteResult, NLSQLExample, WrenContext


@dataclass
class WrenCommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str

    def to_dict(self) -> dict[str, object]:
        return {
            "args": self.args,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


class WrenCliAdapter(WrenAdapter):
    def __init__(
        self,
        wren_bin: Path,
        project_dir: Path,
        wren_home: Path,
        timeout_seconds: int = 60,
    ) -> None:
        self.wren_bin = wren_bin
        self.project_dir = project_dir
        self.wren_home = wren_home
        self.timeout_seconds = timeout_seconds

    def get_context(self, question: str) -> WrenContext:
        show = self._run(["context", "show", "--output", "json"])
        raw: dict[str, object] = {}
        if show.returncode == 0 and show.stdout.strip():
            raw = json.loads(show.stdout)

        describe = self._run(["memory", "describe"])
        text = describe.stdout.strip() if describe.returncode == 0 else show.stdout.strip()
        return WrenContext(text=text, raw=raw)

    def recall_examples(self, question: str, limit: int = 3) -> list[NLSQLExample]:
        examples_dir = self.project_dir / "knowledge" / "sql"
        if not examples_dir.exists():
            return []
        examples: list[NLSQLExample] = []
        for path in examples_dir.glob("*.md"):
            parsed = _parse_front_matter(path)
            if parsed.get("nl") and parsed.get("sql"):
                examples.append(
                    NLSQLExample(
                        question=str(parsed["nl"]),
                        sql=str(parsed["sql"]),
                        source=str(parsed.get("source") or path.name),
                    )
                )
        scored = sorted(examples, key=lambda item: _score_example(question, item), reverse=True)
        return scored[:limit]

    def dry_plan(self, sql: str) -> DryRunResult:
        result = self._run(["dry-plan", "--sql", sql])
        return DryRunResult(
            ok=result.returncode == 0,
            message=(result.stderr or result.stdout).strip(),
            expanded_sql=result.stdout.strip() if result.returncode == 0 else None,
            raw=result.to_dict(),
        )

    def dry_run(self, sql: str) -> DryRunResult:
        result = self._run(["dry-run", "--sql", sql])
        return DryRunResult(
            ok=result.returncode == 0,
            message=(result.stdout or result.stderr).strip(),
            raw=result.to_dict(),
        )

    def execute(self, sql: str, limit: int = 100) -> ExecuteResult:
        bounded_sql, cli_limit = _bounded_query(sql, limit)
        args = ["query", "--sql", bounded_sql, "--output", "json", "--quiet"]
        if cli_limit is not None:
            args.extend(["--limit", str(cli_limit)])
        result = self._run(args)
        if result.returncode != 0:
            return ExecuteResult(ok=False, error=(result.stderr or result.stdout).strip(), raw=result.to_dict())
        try:
            rows = _parse_json_rows(result.stdout)
        except json.JSONDecodeError as exc:
            return ExecuteResult(ok=False, error=f"Failed to parse Wren JSON output: {exc}", raw=result.to_dict())
        return ExecuteResult(ok=True, rows=rows, raw=result.to_dict())

    def _run(self, args: list[str]) -> WrenCommandResult:
        env = os.environ.copy()
        env["WREN_HOME"] = str(self.wren_home)
        env["PYTHONIOENCODING"] = "utf-8"
        completed = subprocess.run(
            [str(self.wren_bin), *args],
            cwd=str(self.project_dir),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout_seconds,
            check=False,
        )
        return WrenCommandResult(
            args=args,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def _parse_json_rows(stdout: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    text = stdout.strip()
    if not text:
        return rows
    if text.startswith("["):
        loaded = json.loads(text)
        if isinstance(loaded, list):
            return [dict(item) for item in loaded]
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        loaded = json.loads(line)
        if isinstance(loaded, dict):
            rows.append(loaded)
    return rows


_TRAILING_LIMIT_PATTERN = re.compile(
    r"\bLIMIT\s+(?P<count>\d+)(?P<offset>\s+OFFSET\s+\d+)?\s*$",
    re.IGNORECASE,
)


def _bounded_query(sql: str, limit: int) -> tuple[str, int | None]:
    bounded_limit = max(1, int(limit))
    normalized_sql = sql.strip().rstrip(";").rstrip()
    match = _TRAILING_LIMIT_PATTERN.search(normalized_sql)
    if not match:
        return normalized_sql, bounded_limit
    requested_limit = int(match.group("count"))
    if requested_limit > bounded_limit:
        start, end = match.span("count")
        normalized_sql = f"{normalized_sql[:start]}{bounded_limit}{normalized_sql[end:]}"
    return normalized_sql, None


def _parse_front_matter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    data: dict[str, str] = {}
    for raw_line in parts[1].splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip("'\"")
    return data


def _score_example(question: str, example: NLSQLExample) -> int:
    question_tokens = set(_tokens(question))
    example_tokens = set(_tokens(example.question + " " + example.sql))
    return len(question_tokens & example_tokens)


def _tokens(text: str) -> list[str]:
    return [part.lower() for part in text.replace("_", " ").split() if len(part) > 2]
