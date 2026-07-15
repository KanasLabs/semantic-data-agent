from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .codex_runtime import prepare_codex_enrichment
from .inspect import inspect_sqlite_schema
from .revision_engine import (
    register_existing_candidate,
    resume_revision,
    retry_revision_evals,
    revise_candidate,
)
from .revision_store import RiskLevel
from .revision_starrocks import StarRocksRevisionConfig
from .review_workflow import (
    answer_review_question,
    approve_candidate,
    publish_candidate,
    reject_candidate,
    review_candidate,
    rollback_context,
)
from .skill_onboarding import prepare_sqlite_skill_onboarding
from .smoke_eval import make_smoke_eval
from .sqlite_onboarding import generate_from_sqlite, validate_project
from .starrocks_query import (
    MySQLdbStarRocksExecutor,
    StarRocksConnectionConfig,
    StarRocksQueryError,
    StarRocksQueryExecutionError,
    StarRocksQueryPolicy,
    run_starrocks_query,
)
from .starrocks_onboarding import prepare_starrocks_skill_onboarding


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="data-subagent-context-builder")
    parser.add_argument("--project-root", default=".")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--sqlite-path", required=True)
    inspect_parser.add_argument("--project-name", default=None)
    inspect_parser.add_argument("--output", default=None, help="Optional Markdown report path.")
    inspect_parser.add_argument("--json-output", default=None, help="Optional JSON report path.")

    generate_parser = subparsers.add_parser("generate-from-db")
    generate_parser.add_argument("--sqlite-path", required=True)
    generate_parser.add_argument("--project-name", required=True)
    generate_parser.add_argument("--project-dir", required=True)
    generate_parser.add_argument("--duckdb-path", required=True)
    generate_parser.add_argument("--mode", choices=["skill", "draft"], default="skill")
    _add_wren_args(generate_parser)
    generate_parser.add_argument("--smoke-sql", default=None)
    generate_parser.add_argument("--report-path", default=None)
    generate_parser.add_argument("--force", action="store_true")
    generate_parser.add_argument("--instructions", default=None)
    generate_parser.add_argument("--prompt-output", default=None)
    generate_parser.add_argument("--execute", action="store_true")
    generate_parser.add_argument("--max-repair-rounds", type=int, default=2)
    generate_parser.add_argument("--no-post-validate", action="store_true")
    _add_codex_args(generate_parser)

    draft_parser = subparsers.add_parser("generate-schema-draft")
    draft_parser.add_argument("--sqlite-path", required=True)
    draft_parser.add_argument("--project-name", required=True)
    draft_parser.add_argument("--project-dir", required=True)
    draft_parser.add_argument("--duckdb-path", required=True)
    _add_wren_args(draft_parser)
    draft_parser.add_argument("--smoke-sql", default=None)
    draft_parser.add_argument("--report-path", default=None)
    draft_parser.add_argument("--force", action="store_true")

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--project-name", default=None)
    validate_parser.add_argument("--project-dir", required=True)
    _add_wren_args(validate_parser)
    validate_parser.add_argument("--smoke-sql", default=None)
    validate_parser.add_argument("--report-path", default=None)

    codex_parser = subparsers.add_parser("enrich-with-codex")
    codex_parser.add_argument("--project-dir", required=True)
    _add_wren_args(codex_parser)
    codex_parser.add_argument("--smoke-sql", default=None)
    codex_parser.add_argument("--instructions", default=None)
    codex_parser.add_argument("--prompt-output", default=None)
    codex_parser.add_argument("--execute", action="store_true")
    _add_codex_args(codex_parser)

    register_parser = subparsers.add_parser("register-candidate")
    register_parser.add_argument("--registry-root", default="data/context_registry")
    register_parser.add_argument("--context-id", required=True)
    register_parser.add_argument("--project-dir", required=True)
    register_parser.add_argument("--version", type=int, default=1)

    revise_parser = subparsers.add_parser("revise-candidate")
    revise_parser.add_argument("--registry-root", default="data/context_registry")
    revise_parser.add_argument("--candidate", required=True)
    revise_parser.add_argument("--expected-base-version", type=int, default=None)
    revise_parser.add_argument("--instruction", required=True)
    revise_parser.add_argument("--requested-scope", action="append", default=None)
    revise_parser.add_argument(
        "--risk-level",
        choices=[level.value for level in RiskLevel],
        default=RiskLevel.MEDIUM.value,
    )
    revise_parser.add_argument("--smoke-sql", default=None)
    revise_parser.add_argument("--execute", action="store_true")
    revise_parser.add_argument("--max-repair-rounds", type=int, default=2)
    revise_parser.add_argument("--no-evals", action="store_true")
    revise_parser.add_argument("--regression-suite", action="append", default=None)
    revise_parser.add_argument("--smoke-max-cases", type=int, default=3)
    revise_parser.add_argument("--no-relationship-smoke", action="store_true")
    revise_parser.add_argument("--eval-model", default=None)
    revise_parser.add_argument("--eval-query-limit", type=int, default=None)
    revise_parser.add_argument("--eval-timeout-seconds", type=int, default=1800)
    _add_wren_args(revise_parser)
    revise_parser.add_argument("--codex-bin", default="codex")
    revise_parser.add_argument("--codex-model", default=None)
    revise_parser.add_argument("--codex-timeout-seconds", type=int, default=900)
    _add_revision_starrocks_args(revise_parser)

    review_parser = subparsers.add_parser("review-candidate")
    review_parser.add_argument("--registry-root", default="data/context_registry")
    review_parser.add_argument("--candidate", required=True)

    answer_parser = subparsers.add_parser("answer-review-question")
    answer_parser.add_argument("--registry-root", default="data/context_registry")
    answer_parser.add_argument("--revision", required=True)
    answer_parser.add_argument("--task", required=True)
    answer_parser.add_argument("--question", required=True)
    answer_parser.add_argument("--answer", required=True)

    resume_parser = subparsers.add_parser("resume-revision")
    resume_parser.add_argument("--registry-root", default="data/context_registry")
    resume_parser.add_argument("--revision", required=True)
    resume_parser.add_argument("--smoke-sql", default=None)
    resume_parser.add_argument("--execute", action="store_true")
    resume_parser.add_argument("--max-repair-rounds", type=int, default=2)
    resume_parser.add_argument("--no-evals", action="store_true")
    resume_parser.add_argument("--regression-suite", action="append", default=None)
    resume_parser.add_argument("--smoke-max-cases", type=int, default=3)
    resume_parser.add_argument("--no-relationship-smoke", action="store_true")
    resume_parser.add_argument("--eval-model", default=None)
    resume_parser.add_argument("--eval-query-limit", type=int, default=None)
    resume_parser.add_argument("--eval-timeout-seconds", type=int, default=1800)
    _add_wren_args(resume_parser)
    resume_parser.add_argument("--codex-bin", default="codex")
    resume_parser.add_argument("--codex-model", default=None)
    resume_parser.add_argument("--codex-timeout-seconds", type=int, default=900)
    _add_revision_starrocks_args(resume_parser)

    retry_eval_parser = subparsers.add_parser("retry-revision-evals")
    retry_eval_parser.add_argument("--registry-root", default="data/context_registry")
    retry_eval_parser.add_argument("--revision", required=True)
    retry_eval_parser.add_argument("--smoke-sql", default=None)
    retry_eval_parser.add_argument("--regression-suite", action="append", default=None)
    retry_eval_parser.add_argument("--smoke-max-cases", type=int, default=3)
    retry_eval_parser.add_argument("--no-relationship-smoke", action="store_true")
    retry_eval_parser.add_argument("--eval-model", default=None)
    retry_eval_parser.add_argument("--eval-query-limit", type=int, default=None)
    retry_eval_parser.add_argument("--eval-timeout-seconds", type=int, default=1800)
    _add_wren_args(retry_eval_parser)

    approve_parser = subparsers.add_parser("approve-candidate")
    approve_parser.add_argument("--registry-root", default="data/context_registry")
    approve_parser.add_argument("--candidate", required=True)
    approve_parser.add_argument("--note", required=True)

    reject_parser = subparsers.add_parser("reject-candidate")
    reject_parser.add_argument("--registry-root", default="data/context_registry")
    reject_parser.add_argument("--candidate", required=True)
    reject_parser.add_argument("--reason", required=True)

    publish_parser = subparsers.add_parser("publish-candidate")
    publish_parser.add_argument("--registry-root", default="data/context_registry")
    publish_parser.add_argument("--candidate", required=True)

    rollback_parser = subparsers.add_parser("rollback-context")
    rollback_parser.add_argument("--registry-root", default="data/context_registry")
    rollback_parser.add_argument("--context-id", required=True)
    rollback_parser.add_argument("--candidate", default=None)

    smoke_parser = subparsers.add_parser("make-smoke-eval")
    smoke_parser.add_argument("--project-dir", required=True)
    smoke_parser.add_argument("--output", required=True)
    smoke_parser.add_argument("--dataset", default=None)
    smoke_parser.add_argument("--db-id", default=None)
    smoke_parser.add_argument("--max-cases", type=int, default=3)
    smoke_parser.add_argument("--include-relationship-case", action="store_true")

    starrocks_parser = subparsers.add_parser("starrocks-query")
    starrocks_parser.add_argument("--host", required=True)
    starrocks_parser.add_argument("--port", type=int, default=9030)
    starrocks_parser.add_argument("--database", required=True)
    starrocks_parser.add_argument("--user", required=True)
    starrocks_parser.add_argument("--password-env", default="CONTEXT_BUILDER_STARROCKS_PASSWORD")
    starrocks_parser.add_argument("--allow-empty-password", action="store_true")
    starrocks_parser.add_argument("--sql", required=True)
    starrocks_parser.add_argument("--allowed-catalog", action="append", default=None)
    starrocks_parser.add_argument("--allowed-database", action="append", default=None)
    starrocks_parser.add_argument("--max-rows", type=int, default=100)
    starrocks_parser.add_argument("--query-timeout-seconds", type=int, default=15)
    starrocks_parser.add_argument("--allow-information-schema", action="store_true")
    starrocks_parser.add_argument("--evidence-path", required=True)
    starrocks_parser.add_argument("--include-evidence-rows", action="store_true")

    starrocks_generate_parser = subparsers.add_parser("generate-from-starrocks")
    starrocks_generate_parser.add_argument("--project-name", required=True)
    starrocks_generate_parser.add_argument("--project-dir", required=True)
    starrocks_generate_parser.add_argument("--host", required=True)
    starrocks_generate_parser.add_argument("--port", type=int, default=9030)
    starrocks_generate_parser.add_argument("--database", required=True)
    starrocks_generate_parser.add_argument("--user", required=True)
    starrocks_generate_parser.add_argument(
        "--password-env", default="CONTEXT_BUILDER_STARROCKS_PASSWORD"
    )
    starrocks_generate_parser.add_argument("--allow-empty-password", action="store_true")
    starrocks_generate_parser.add_argument("--profile-name", default=None)
    starrocks_generate_parser.add_argument("--allowed-catalog", action="append", default=None)
    starrocks_generate_parser.add_argument("--allowed-database", action="append", default=None)
    starrocks_generate_parser.add_argument("--max-query-rows", type=int, default=100)
    starrocks_generate_parser.add_argument("--query-timeout-seconds", type=int, default=15)
    starrocks_generate_parser.add_argument("--smoke-sql", default=None)
    starrocks_generate_parser.add_argument("--report-path", default=None)
    starrocks_generate_parser.add_argument("--force", action="store_true")
    starrocks_generate_parser.add_argument("--instructions", default=None)
    starrocks_generate_parser.add_argument("--prompt-output", default=None)
    starrocks_generate_parser.add_argument("--execute", action="store_true")
    starrocks_generate_parser.add_argument("--max-repair-rounds", type=int, default=2)
    starrocks_generate_parser.add_argument("--no-post-validate", action="store_true")
    _add_wren_args(starrocks_generate_parser)
    _add_codex_args(starrocks_generate_parser)

    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()

    if args.command == "inspect":
        result = inspect_sqlite_schema(
            sqlite_path=Path(args.sqlite_path),
            project_name=args.project_name,
            report_path=Path(args.output) if args.output else None,
            json_output_path=Path(args.json_output) if args.json_output else None,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "generate-from-db":
        if args.mode == "draft":
            result = _generate_schema_draft(args, project_root)
        else:
            result = prepare_sqlite_skill_onboarding(
                sqlite_path=Path(args.sqlite_path),
                project_name=args.project_name,
                project_dir=Path(args.project_dir),
                duckdb_path=Path(args.duckdb_path),
                wren_home=_wren_home(args, project_root),
                wren_bin=_wren_bin(args, project_root),
                project_root=project_root,
                smoke_sql=args.smoke_sql,
                extra_instructions=args.instructions,
                prompt_output_path=Path(args.prompt_output) if args.prompt_output else None,
                execute_codex=args.execute,
                force=args.force,
                timeout_seconds=args.timeout_seconds,
                codex_bin=args.codex_bin,
                codex_model=args.codex_model,
                codex_last_message_path=Path(args.codex_last_message)
                if args.codex_last_message
                else None,
                codex_timeout_seconds=args.codex_timeout_seconds,
                max_repair_rounds=args.max_repair_rounds,
                post_validate=not args.no_post_validate,
                report_path=Path(args.report_path) if args.report_path else None,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "generate-schema-draft":
        result = _generate_schema_draft(args, project_root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "register-candidate":
        result = register_existing_candidate(
            registry_root=_registry_root(args.registry_root, project_root),
            context_id=args.context_id,
            project_dir=Path(args.project_dir),
            version=args.version,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "revise-candidate":
        result = revise_candidate(
            registry_root=_registry_root(args.registry_root, project_root),
            base_candidate_id=args.candidate,
            expected_base_version=args.expected_base_version,
            user_instruction=args.instruction,
            requested_scope=args.requested_scope,
            risk_level=RiskLevel(args.risk_level),
            project_root=project_root,
            wren_home=_wren_home(args, project_root),
            wren_bin=_wren_bin(args, project_root),
            smoke_sql=args.smoke_sql,
            execute_codex=args.execute,
            timeout_seconds=args.timeout_seconds,
            codex_bin=args.codex_bin,
            codex_model=args.codex_model,
            codex_timeout_seconds=args.codex_timeout_seconds,
            max_repair_rounds=args.max_repair_rounds,
            run_evals=not args.no_evals,
            regression_suites=[_project_path(path, project_root) for path in args.regression_suite]
            if args.regression_suite
            else None,
            smoke_max_cases=args.smoke_max_cases,
            include_relationship_smoke=not args.no_relationship_smoke,
            eval_model=args.eval_model,
            eval_query_limit=args.eval_query_limit,
            eval_timeout_seconds=args.eval_timeout_seconds,
            starrocks_config=_revision_starrocks_config(args),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "review-candidate":
        result = review_candidate(
            registry_root=_registry_root(args.registry_root, project_root),
            candidate_id=args.candidate,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "answer-review-question":
        result = answer_review_question(
            registry_root=_registry_root(args.registry_root, project_root),
            revision_id=args.revision,
            task_id=args.task,
            question_id=args.question,
            answer=args.answer,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "resume-revision":
        result = resume_revision(
            registry_root=_registry_root(args.registry_root, project_root),
            revision_id=args.revision,
            project_root=project_root,
            wren_home=_wren_home(args, project_root),
            wren_bin=_wren_bin(args, project_root),
            smoke_sql=args.smoke_sql,
            execute_codex=args.execute,
            timeout_seconds=args.timeout_seconds,
            codex_bin=args.codex_bin,
            codex_model=args.codex_model,
            codex_timeout_seconds=args.codex_timeout_seconds,
            max_repair_rounds=args.max_repair_rounds,
            run_evals=not args.no_evals,
            regression_suites=[_project_path(path, project_root) for path in args.regression_suite]
            if args.regression_suite
            else None,
            smoke_max_cases=args.smoke_max_cases,
            include_relationship_smoke=not args.no_relationship_smoke,
            eval_model=args.eval_model,
            eval_query_limit=args.eval_query_limit,
            eval_timeout_seconds=args.eval_timeout_seconds,
            starrocks_config=_revision_starrocks_config(args),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "approve-candidate":
        result = approve_candidate(
            registry_root=_registry_root(args.registry_root, project_root),
            candidate_id=args.candidate,
            approval_note=args.note,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "retry-revision-evals":
        result = retry_revision_evals(
            registry_root=_registry_root(args.registry_root, project_root),
            revision_id=args.revision,
            project_root=project_root,
            wren_home=_wren_home(args, project_root),
            wren_bin=_wren_bin(args, project_root),
            smoke_sql=args.smoke_sql,
            regression_suites=[_project_path(path, project_root) for path in args.regression_suite]
            if args.regression_suite
            else None,
            smoke_max_cases=args.smoke_max_cases,
            include_relationship_smoke=not args.no_relationship_smoke,
            eval_model=args.eval_model,
            eval_query_limit=args.eval_query_limit,
            eval_timeout_seconds=args.eval_timeout_seconds,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "reject-candidate":
        result = reject_candidate(
            registry_root=_registry_root(args.registry_root, project_root),
            candidate_id=args.candidate,
            reason=args.reason,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "publish-candidate":
        result = publish_candidate(
            registry_root=_registry_root(args.registry_root, project_root),
            candidate_id=args.candidate,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "rollback-context":
        result = rollback_context(
            registry_root=_registry_root(args.registry_root, project_root),
            context_id=args.context_id,
            target_candidate_id=args.candidate,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "make-smoke-eval":
        result = make_smoke_eval(
            wren_project_dir=Path(args.project_dir),
            output_path=Path(args.output),
            dataset=args.dataset,
            db_id=args.db_id,
            max_cases=args.max_cases,
            include_relationship_case=args.include_relationship_case,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "starrocks-query":
        password = os.environ.get(args.password_env)
        if password is None and not args.allow_empty_password:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": f"Required password environment variable is not set: {args.password_env}",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            raise SystemExit(2)
        password = password or ""
        policy = StarRocksQueryPolicy(
            allowed_catalogs=tuple(args.allowed_catalog or ["default_catalog"]),
            allowed_databases=tuple(args.allowed_database or [args.database]),
            max_rows=args.max_rows,
            timeout_seconds=args.query_timeout_seconds,
            allow_information_schema=args.allow_information_schema,
        )
        executor = MySQLdbStarRocksExecutor(
            StarRocksConnectionConfig(
                host=args.host,
                port=args.port,
                database=args.database,
                user=args.user,
                password=password,
            )
        )
        try:
            result = run_starrocks_query(
                sql=args.sql,
                database=args.database,
                policy=policy,
                evidence_path=Path(args.evidence_path),
                executor=executor,
                include_evidence_rows=args.include_evidence_rows,
            )
        except (StarRocksQueryError, StarRocksQueryExecutionError) as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
            raise SystemExit(2) from exc
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "generate-from-starrocks":
        result = prepare_starrocks_skill_onboarding(
            project_name=args.project_name,
            project_dir=Path(args.project_dir),
            project_root=project_root,
            wren_home=_wren_home(args, project_root),
            wren_bin=_wren_bin(args, project_root),
            host=args.host,
            port=args.port,
            database=args.database,
            user=args.user,
            password_env=args.password_env,
            allow_empty_password=args.allow_empty_password,
            profile_name=args.profile_name,
            allowed_catalogs=tuple(args.allowed_catalog or ["default_catalog"]),
            allowed_databases=tuple(args.allowed_database or [args.database]),
            max_query_rows=args.max_query_rows,
            query_timeout_seconds=args.query_timeout_seconds,
            smoke_sql=args.smoke_sql,
            extra_instructions=args.instructions,
            prompt_output_path=Path(args.prompt_output) if args.prompt_output else None,
            execute_codex=args.execute,
            force=args.force,
            timeout_seconds=args.timeout_seconds,
            codex_bin=args.codex_bin,
            codex_model=args.codex_model,
            codex_last_message_path=Path(args.codex_last_message)
            if args.codex_last_message
            else None,
            codex_timeout_seconds=args.codex_timeout_seconds,
            max_repair_rounds=args.max_repair_rounds,
            post_validate=not args.no_post_validate,
            report_path=Path(args.report_path) if args.report_path else None,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "enrich-with-codex":
        result = prepare_codex_enrichment(
            project_root=project_root,
            wren_project_dir=Path(args.project_dir),
            wren_home=_wren_home(args, project_root),
            wren_bin=_wren_bin(args, project_root),
            smoke_sql=args.smoke_sql,
            extra_instructions=args.instructions,
            prompt_output_path=Path(args.prompt_output) if args.prompt_output else None,
            execute=args.execute,
            codex_bin=args.codex_bin,
            codex_model=args.codex_model,
            last_message_path=Path(args.codex_last_message) if args.codex_last_message else None,
            timeout_seconds=args.codex_timeout_seconds,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "validate":
        result = validate_project(
            project_name=args.project_name,
            project_dir=Path(args.project_dir),
            wren_home=_wren_home(args, project_root),
            wren_bin=_wren_bin(args, project_root),
            smoke_sql=args.smoke_sql,
            report_path=Path(args.report_path) if args.report_path else None,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))


def _add_wren_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--wren-home", default=None)
    parser.add_argument("--wren-bin", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=60)


def _add_codex_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--codex-model", default=None)
    parser.add_argument("--codex-last-message", default=None)
    parser.add_argument("--codex-timeout-seconds", type=int, default=900)


def _add_revision_starrocks_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--starrocks-host", default=None)
    parser.add_argument("--starrocks-port", type=int, default=9030)
    parser.add_argument("--starrocks-database", default=None)
    parser.add_argument("--starrocks-user", default=None)
    parser.add_argument(
        "--starrocks-password-env",
        default="CONTEXT_BUILDER_STARROCKS_PASSWORD",
    )
    parser.add_argument("--starrocks-allow-empty-password", action="store_true")
    parser.add_argument("--starrocks-allowed-catalog", action="append", default=None)
    parser.add_argument("--starrocks-allowed-database", action="append", default=None)
    parser.add_argument("--starrocks-max-query-rows", type=int, default=100)
    parser.add_argument("--starrocks-query-timeout-seconds", type=int, default=15)


def _generate_schema_draft(args: argparse.Namespace, project_root: Path) -> dict[str, object]:
    result = generate_from_sqlite(
        sqlite_path=Path(args.sqlite_path),
        project_name=args.project_name,
        project_dir=Path(args.project_dir),
        duckdb_path=Path(args.duckdb_path),
        wren_home=_wren_home(args, project_root),
        wren_bin=_wren_bin(args, project_root),
        smoke_sql=args.smoke_sql,
        report_path=Path(args.report_path) if args.report_path else None,
        force=args.force,
        timeout_seconds=args.timeout_seconds,
    )
    result["mode"] = "draft"
    result["warning"] = (
        "Schema draft mode writes mechanical MDL from database metadata. "
        "Use generate-from-db --mode skill for the recommended Wren generate-mdl skill path."
    )
    return result


def _wren_home(args: argparse.Namespace, project_root: Path) -> Path:
    return Path(args.wren_home).resolve() if args.wren_home else project_root / "data" / "wren" / "home"


def _wren_bin(args: argparse.Namespace, project_root: Path) -> Path:
    return Path(args.wren_bin).resolve() if args.wren_bin else project_root / ".venv-wren" / "Scripts" / "wren.exe"


def _registry_root(value: str, project_root: Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (project_root / path).resolve()


def _project_path(value: str, project_root: Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (project_root / path).resolve()


def _revision_starrocks_config(args: argparse.Namespace) -> StarRocksRevisionConfig | None:
    values = (args.starrocks_host, args.starrocks_database, args.starrocks_user)
    if not any(values):
        return None
    if not all(values):
        raise ValueError(
            "Revision StarRocks access requires --starrocks-host, --starrocks-database, and --starrocks-user."
        )
    return StarRocksRevisionConfig(
        host=args.starrocks_host,
        port=args.starrocks_port,
        database=args.starrocks_database,
        user=args.starrocks_user,
        password_env=args.starrocks_password_env,
        allow_empty_password=args.starrocks_allow_empty_password,
        allowed_catalogs=tuple(args.starrocks_allowed_catalog or ["default_catalog"]),
        allowed_databases=tuple(args.starrocks_allowed_database or [args.starrocks_database]),
        max_query_rows=args.starrocks_max_query_rows,
        query_timeout_seconds=args.starrocks_query_timeout_seconds,
    )


if __name__ == "__main__":
    main()
