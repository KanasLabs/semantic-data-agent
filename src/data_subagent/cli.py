from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from .adapters.wren_cli import WrenCliAdapter
from .agent import DataSubagent
from .config import SubagentConfig
from .eval_runner import run_eval_suite
from .llm_deepseek import DeepSeekLLMAdapter
from .trace_store import JsonlTraceStore


def main() -> None:
    parser = argparse.ArgumentParser(prog="data-subagent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_parser = subparsers.add_parser("ask")
    ask_parser.add_argument("question")
    ask_parser.add_argument("--project-root", default=".")
    _add_wren_runtime_args(ask_parser)
    ask_parser.add_argument("--model", default=None)
    ask_parser.add_argument("--limit", type=int, default=None)
    ask_parser.add_argument(
        "--inject-initial-sql",
        default=None,
        help="Debug/eval only: force the first SQL attempt, then let repair_sql handle Wren errors.",
    )

    doctor_parser = subparsers.add_parser("doctor-wren")
    doctor_parser.add_argument("--project-root", default=".")
    _add_wren_runtime_args(doctor_parser)

    eval_parser = subparsers.add_parser("eval")
    eval_parser.add_argument("--suite", required=True)
    eval_parser.add_argument("--project-root", default=".")
    _add_wren_runtime_args(eval_parser)
    eval_parser.add_argument("--model", default=None)
    eval_parser.add_argument("--limit", "--max-cases", dest="case_limit", type=int, default=None)
    eval_parser.add_argument("--query-limit", type=int, default=None)
    eval_parser.add_argument("--output-dir", default="data/evals/runs")
    eval_parser.add_argument("--report-dir", default="data/evals/reports")
    eval_parser.add_argument("--suite-name", default=None)

    args = parser.parse_args()
    config = _apply_runtime_overrides(SubagentConfig.default(Path(args.project_root)), args)

    if args.command == "doctor-wren":
        wren = _build_wren(config)
        context = wren.get_context("doctor")
        dry = wren.dry_run("select count(*) as order_count from orders")
        print(
            json.dumps(
                {
                    "wren_bin": str(config.wren_bin),
                    "wren_project_dir": str(config.wren_project_dir),
                    "wren_home": str(config.wren_home),
                    "models": [m.get("name") for m in context.raw.get("models", [])],
                    "dry_run_ok": dry.ok,
                    "dry_run_message": dry.message,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if args.command in {"ask", "eval"}:
        if args.model:
            config = SubagentConfig(
                **{**config.__dict__, "deepseek_model": args.model}
            )
        llm = DeepSeekLLMAdapter(
            api_key=config.read_deepseek_api_key(),
            model=config.deepseek_model,
            base_url=config.deepseek_base_url,
            timeout_seconds=config.llm_timeout_seconds,
        )
        agent = DataSubagent(
            wren=_build_wren(config),
            llm=llm,
            trace_store=JsonlTraceStore(config.trace_path),
            max_repair_attempts=config.max_repair_attempts,
            query_limit=_query_limit_for_command(args, config),
        )

    if args.command == "ask":
        constraints = (
            {"debug_initial_sql": args.inject_initial_sql}
            if args.inject_initial_sql
            else None
        )
        answer = agent.ask_data_question(args.question, constraints=constraints)
        print(json.dumps(answer.to_dict(), ensure_ascii=False, indent=2))
        return

    if args.command == "eval":
        summary = run_eval_suite(
            agent=agent,
            cases_path=Path(args.suite),
            trace_path=config.trace_path,
            output_dir=Path(args.output_dir),
            report_dir=Path(args.report_dir),
            suite_name=args.suite_name,
            limit=args.case_limit,
        )
        print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))


def _build_wren(config: SubagentConfig) -> WrenCliAdapter:
    return WrenCliAdapter(
        wren_bin=config.wren_bin,
        project_dir=config.wren_project_dir,
        wren_home=config.wren_home,
        timeout_seconds=config.wren_timeout_seconds,
    )


def _add_wren_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--wren-project-dir",
        default=None,
        help="Override the Wren project directory for this command.",
    )
    parser.add_argument(
        "--wren-home",
        default=None,
        help="Override WREN_HOME for this command.",
    )
    parser.add_argument(
        "--wren-bin",
        default=None,
        help="Override the Wren CLI binary path for this command.",
    )


def _apply_runtime_overrides(config: SubagentConfig, args: argparse.Namespace) -> SubagentConfig:
    updates = {}
    if getattr(args, "wren_project_dir", None):
        updates["wren_project_dir"] = Path(args.wren_project_dir).resolve()
    if getattr(args, "wren_home", None):
        updates["wren_home"] = Path(args.wren_home).resolve()
    if getattr(args, "wren_bin", None):
        updates["wren_bin"] = Path(args.wren_bin).resolve()
    return replace(config, **updates) if updates else config


def _query_limit_for_command(args: argparse.Namespace, config: SubagentConfig) -> int:
    if args.command == "ask":
        return args.limit or config.query_limit
    return getattr(args, "query_limit", None) or config.query_limit


if __name__ == "__main__":
    main()
