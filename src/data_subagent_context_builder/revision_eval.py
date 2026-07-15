from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Protocol

from .smoke_eval import make_smoke_eval


class RevisionEvalRunner(Protocol):
    def run(
        self,
        *,
        suite_path: Path,
        suite_name: str,
        candidate_project_dir: Path,
        output_dir: Path,
        report_dir: Path,
    ) -> dict[str, Any]:
        ...


class DataSubagentCliEvalRunner:
    def __init__(
        self,
        *,
        project_root: Path,
        wren_home: Path,
        wren_bin: Path,
        python_bin: Path | None = None,
        model: str | None = None,
        query_limit: int | None = None,
        timeout_seconds: int = 1800,
    ) -> None:
        self.project_root = project_root.resolve()
        self.wren_home = wren_home.resolve()
        self.wren_bin = wren_bin.resolve()
        self.python_bin = (python_bin or Path(sys.executable)).resolve()
        self.model = model
        self.query_limit = query_limit
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        *,
        suite_path: Path,
        suite_name: str,
        candidate_project_dir: Path,
        output_dir: Path,
        report_dir: Path,
    ) -> dict[str, Any]:
        args = [
            str(self.python_bin),
            "-m",
            "data_subagent.cli",
            "eval",
            "--project-root",
            str(self.project_root),
            "--suite",
            str(suite_path.resolve()),
            "--suite-name",
            suite_name,
            "--wren-project-dir",
            str(candidate_project_dir.resolve()),
            "--wren-home",
            str(self.wren_home),
            "--wren-bin",
            str(self.wren_bin),
            "--output-dir",
            str(output_dir.resolve()),
            "--report-dir",
            str(report_dir.resolve()),
        ]
        if self.model:
            args.extend(["--model", self.model])
        if self.query_limit:
            args.extend(["--query-limit", str(self.query_limit)])
        env = os.environ.copy()
        source_path = str(self.project_root / "src")
        env["PYTHONPATH"] = os.pathsep.join(
            item for item in (source_path, env.get("PYTHONPATH", "")) if item
        )
        try:
            completed = subprocess.run(
                args,
                cwd=self.project_root,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "ok": False,
                "args": args[1:],
                "returncode": 124,
                "stdout": _decoded_timeout_output(exc.stdout),
                "stderr": _decoded_timeout_output(exc.stderr)
                or f"Eval timed out after {self.timeout_seconds} seconds.",
                "summary": None,
            }
        summary: dict[str, Any] | None = None
        parse_error: str | None = None
        if completed.stdout.strip():
            try:
                loaded = json.loads(completed.stdout)
                if isinstance(loaded, dict):
                    summary = loaded
                else:
                    parse_error = "Eval CLI output was not a JSON object."
            except json.JSONDecodeError as exc:
                parse_error = f"Invalid Eval CLI JSON output: {exc}"
        else:
            parse_error = "Eval CLI produced no JSON output."
        failed = summary.get("failed") if summary else None
        ok = completed.returncode == 0 and parse_error is None and failed == 0
        stderr = completed.stderr
        if parse_error:
            stderr = f"{stderr.rstrip()}\n{parse_error}".strip()
        return {
            "ok": ok,
            "args": args[1:],
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": stderr,
            "summary": summary,
        }


def run_revision_evals(
    *,
    revision_id: str,
    candidate_project_dir: Path,
    revision_dir: Path,
    eval_runner: RevisionEvalRunner,
    regression_suites: list[Path] | None = None,
    smoke_max_cases: int = 3,
    include_relationship_smoke: bool = True,
) -> dict[str, Any]:
    eval_dir = revision_dir / "evals"
    generated_smoke_path = eval_dir / "generated_smoke.jsonl"
    smoke_generation = make_smoke_eval(
        wren_project_dir=candidate_project_dir,
        output_path=generated_smoke_path,
        max_cases=smoke_max_cases,
        include_relationship_case=include_relationship_smoke,
    )
    smoke_result = eval_runner.run(
        suite_path=generated_smoke_path,
        suite_name=_revision_suite_name(revision_id, "smoke"),
        candidate_project_dir=candidate_project_dir,
        output_dir=eval_dir / "runs",
        report_dir=eval_dir / "reports",
    )
    smoke_artifact = {
        "ok": bool(smoke_result.get("ok")),
        "generation": smoke_generation,
        "execution": smoke_result,
    }
    _write_json(revision_dir / "smoke_eval.json", smoke_artifact)

    regression_results: list[dict[str, Any]] = []
    for index, suite_path in enumerate(regression_suites or []):
        resolved_suite = suite_path.resolve()
        if not resolved_suite.is_file():
            regression_results.append(
                {
                    "ok": False,
                    "suite_path": str(resolved_suite),
                    "error": "Regression suite not found.",
                }
            )
            continue
        execution = eval_runner.run(
            suite_path=resolved_suite,
            suite_name=_revision_suite_name(
                revision_id,
                "regression",
                index=index,
                suite_stem=resolved_suite.stem,
            ),
            candidate_project_dir=candidate_project_dir,
            output_dir=eval_dir / "runs",
            report_dir=eval_dir / "reports",
        )
        regression_results.append(
            {
                "ok": bool(execution.get("ok")),
                "suite_path": str(resolved_suite),
                "execution": execution,
            }
        )
    regression_artifact = {
        "ok": all(item["ok"] for item in regression_results),
        "suites": regression_results,
    }
    _write_json(revision_dir / "regression_eval.json", regression_artifact)
    return {
        "ok": bool(smoke_artifact["ok"] and regression_artifact["ok"]),
        "smoke": smoke_artifact,
        "regression": regression_artifact,
    }


def eval_test_coverage(eval_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not eval_result:
        return []
    coverage: list[dict[str, Any]] = []
    smoke = eval_result.get("smoke")
    if isinstance(smoke, dict):
        generation = smoke.get("generation") if isinstance(smoke.get("generation"), dict) else {}
        coverage.append(
            {
                "kind": "smoke",
                "suite": generation.get("output_path"),
                "case_count": generation.get("emitted"),
                "passed": bool(smoke.get("ok")),
            }
        )
    regression = eval_result.get("regression")
    suites = regression.get("suites") if isinstance(regression, dict) else []
    for item in suites if isinstance(suites, list) else []:
        if isinstance(item, dict):
            coverage.append(
                {
                    "kind": "regression",
                    "suite": item.get("suite_path"),
                    "passed": bool(item.get("ok")),
                }
            )
    return coverage


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _decoded_timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _revision_suite_name(
    revision_id: str,
    kind: str,
    *,
    index: int | None = None,
    suite_stem: str | None = None,
) -> str:
    revision_token = revision_id.removeprefix("revision_")[:12]
    parts = ["rev", revision_token, kind]
    if index is not None:
        parts.append(str(index))
    if suite_stem:
        safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "-", suite_stem).strip("-")
        parts.append(safe_stem[:24])
    return "_".join(parts)[:64]
