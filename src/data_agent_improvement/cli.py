from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .feedback import record_feedback
from .ingestion import ingest_eval_run, ingest_traces
from .models import (
    Actor,
    ActorType,
    AuthorityDecisionType,
    AuthorityStatus,
    EvalTargetStatus,
    FeedbackType,
    GroupingMode,
    Provenance,
    ResultContract,
    RootCauseCandidate,
    SemanticConstraints,
    Sentiment,
)
from .report import render_triage_report
from .store import ImprovementStore, new_report_id
from .si2 import execute_semantic_job, prepare_semantic_job, verify_job_integrity
from .triage import (
    approve_eval_target,
    create_eval_target,
    create_grouped_finding,
    dismiss_finding,
    freeze_eval_target,
    mark_eval_target_terminal,
    record_authority_decision,
    submit_eval_target_for_review,
    suggest_groups,
)


def main() -> None:
    _configure_utf8_output()
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project-root", default=".")
    common.add_argument("--registry-root", default="data/improvement_registry")
    parser = argparse.ArgumentParser(prog="data-agent-improvement")
    subparsers = parser.add_subparsers(dest="command", required=True)

    feedback_parser = subparsers.add_parser("record-feedback", parents=[common])
    feedback_parser.add_argument("--trace-id", required=True)
    feedback_parser.add_argument("--trace-path", default="data/traces/data_subagent.jsonl")
    feedback_parser.add_argument("--type", required=True, choices=_enum_values(FeedbackType))
    feedback_parser.add_argument("--sentiment", default="NEUTRAL", choices=_enum_values(Sentiment))
    feedback_parser.add_argument("--comment", default="")
    feedback_parser.add_argument("--expected-answer")
    feedback_parser.add_argument("--expected-sql")
    feedback_parser.add_argument("--business-statement", action="append", default=[])
    feedback_parser.add_argument("--actor-id", default="anonymous-feedback-provider")
    feedback_parser.add_argument(
        "--actor-type",
        default="FEEDBACK_PROVIDER",
        choices=_enum_values(ActorType),
    )
    feedback_parser.add_argument("--source-id", default="interactive-feedback")
    feedback_parser.add_argument("--provenance-statement")
    feedback_parser.add_argument("--authorized-context-id", action="append", default=[])
    feedback_parser.add_argument("--authorized-scope", action="append", default=[])
    feedback_parser.add_argument("--supersedes-feedback-id")
    feedback_parser.add_argument("--allow-missing-trace", action="store_true")

    trace_parser = subparsers.add_parser("ingest-traces", parents=[common])
    trace_parser.add_argument("--trace-path", default="data/traces/data_subagent.jsonl")

    eval_parser = subparsers.add_parser("ingest-eval", parents=[common])
    eval_parser.add_argument("--run-path", required=True)
    eval_parser.add_argument("--run-id", required=True)
    eval_parser.add_argument("--trace-path")

    list_parser = subparsers.add_parser("list-cases", parents=[common])
    list_parser.add_argument("--status")
    list_parser.add_argument("--pretty", action="store_true")

    show_parser = subparsers.add_parser("show-case", parents=[common])
    show_parser.add_argument("--case", required=True)
    show_parser.add_argument("--pretty", action="store_true")

    report_parser = subparsers.add_parser("report", parents=[common])
    report_parser.add_argument("--status")

    authority_parser = subparsers.add_parser("record-authority", parents=[common])
    authority_parser.add_argument("--feedback-id", required=True)
    authority_parser.add_argument(
        "--decision",
        required=True,
        choices=_enum_values(AuthorityDecisionType),
    )
    authority_parser.add_argument("--context-id", action="append", default=[])
    authority_parser.add_argument("--scope", action="append", default=[])
    authority_parser.add_argument("--decided-by", required=True)
    authority_parser.add_argument("--reason", required=True)
    authority_parser.add_argument("--supersedes-authority-id")
    authority_parser.add_argument(
        "--project-authority-confirmed",
        action="store_true",
        help="Required acknowledgement that this local admin action was authorized.",
    )

    subparsers.add_parser("suggest-groups", parents=[common])

    create_finding_parser = subparsers.add_parser("create-finding", parents=[common])
    create_finding_parser.add_argument("--context-id", required=True)
    create_finding_parser.add_argument(
        "--grouping-mode",
        required=True,
        choices=_enum_values(GroupingMode),
    )
    create_finding_parser.add_argument("--case", action="append", required=True)
    create_finding_parser.add_argument(
        "--root-cause",
        required=True,
        choices=_enum_values(RootCauseCandidate),
    )
    create_finding_parser.add_argument("--business-feedback", action="append", default=[])
    create_finding_parser.add_argument("--business-scope", action="append", default=[])

    list_findings_parser = subparsers.add_parser("list-findings", parents=[common])
    list_findings_parser.add_argument("--status")
    list_findings_parser.add_argument("--pretty", action="store_true")

    show_finding_parser = subparsers.add_parser("show-finding", parents=[common])
    show_finding_parser.add_argument("--finding", required=True)
    show_finding_parser.add_argument("--pretty", action="store_true")

    dismiss_finding_parser = subparsers.add_parser("dismiss-finding", parents=[common])
    dismiss_finding_parser.add_argument("--finding", required=True)
    dismiss_finding_parser.add_argument("--reviewer-id", required=True)
    dismiss_finding_parser.add_argument("--reason", required=True)

    create_target_parser = subparsers.add_parser("create-eval-target", parents=[common])
    create_target_parser.add_argument("--finding", required=True)
    create_target_parser.add_argument("--question", required=True)
    create_target_parser.add_argument("--expected-value")
    create_target_parser.add_argument("--numeric-tolerance", type=float)
    create_target_parser.add_argument("--required-filter", action="append", default=[])
    create_target_parser.add_argument("--required-unit", action="append", default=[])
    create_target_parser.add_argument("--forbidden-unit", action="append", default=[])
    create_target_parser.add_argument("--sql-hint", action="append", default=[])
    create_target_parser.add_argument("--evidence-ref", action="append", default=[])
    create_target_parser.add_argument("--supersedes-eval-target-id")

    submit_target_parser = subparsers.add_parser("submit-eval-target", parents=[common])
    submit_target_parser.add_argument("--eval-target", required=True)

    approve_target_parser = subparsers.add_parser("approve-eval-target", parents=[common])
    approve_target_parser.add_argument("--eval-target", required=True)
    approve_target_parser.add_argument("--reviewer-id", required=True)

    freeze_target_parser = subparsers.add_parser("freeze-eval-target", parents=[common])
    freeze_target_parser.add_argument("--eval-target", required=True)

    invalidate_target_parser = subparsers.add_parser(
        "invalidate-eval-target",
        parents=[common],
    )
    invalidate_target_parser.add_argument("--eval-target", required=True)
    invalidate_target_parser.add_argument("--reason", required=True)

    list_targets_parser = subparsers.add_parser("list-eval-targets", parents=[common])
    list_targets_parser.add_argument("--finding")
    list_targets_parser.add_argument("--status")
    list_targets_parser.add_argument("--pretty", action="store_true")

    show_target_parser = subparsers.add_parser("show-eval-target", parents=[common])
    show_target_parser.add_argument("--eval-target", required=True)
    show_target_parser.add_argument("--pretty", action="store_true")

    prepare_job_parser = subparsers.add_parser("prepare-semantic-job", parents=[common])
    prepare_job_parser.add_argument("--eval-target", required=True)
    prepare_job_parser.add_argument("--base-candidate-id", required=True)
    prepare_job_parser.add_argument("--base-snapshot-path", required=True)
    prepare_job_parser.add_argument("--schema-fingerprint")
    prepare_job_parser.add_argument("--snapshot-id")
    prepare_job_parser.add_argument("--risk-level", default="MEDIUM")
    prepare_job_parser.add_argument("--target-repetitions", type=int, default=3)
    prepare_job_parser.add_argument("--timeout-seconds", type=int, default=900)
    prepare_job_parser.add_argument("--max-repair-rounds", type=int, default=2)

    execute_job_parser = subparsers.add_parser("execute-semantic-job", parents=[common])
    execute_job_parser.add_argument("--job", required=True)
    execute_job_parser.add_argument("--context-registry-root", required=True)
    execute_job_parser.add_argument("--wren-home", required=True)
    execute_job_parser.add_argument("--wren-bin", required=True)
    execute_job_parser.add_argument("--codex-bin", default="codex")
    execute_job_parser.add_argument("--codex-model")
    execute_job_parser.add_argument("--regression-suite", action="append", default=[])
    execute_job_parser.add_argument("--smoke-sql")
    execute_job_parser.add_argument("--eval-model")
    execute_job_parser.add_argument("--eval-query-limit", type=int)
    execute_job_parser.add_argument("--eval-timeout-seconds", type=int, default=1800)
    execute_job_parser.add_argument("--execute", action="store_true")
    execute_job_parser.add_argument(
        "--external-isolation-confirmed",
        action="store_true",
    )

    show_job_parser = subparsers.add_parser("show-job", parents=[common])
    show_job_parser.add_argument("--job", required=True)
    show_job_parser.add_argument("--pretty", action="store_true")

    show_job_result_parser = subparsers.add_parser("show-job-result", parents=[common])
    show_job_result_parser.add_argument("--job", required=True)
    show_job_result_parser.add_argument("--pretty", action="store_true")

    verify_job_parser = subparsers.add_parser("verify-job", parents=[common])
    verify_job_parser.add_argument("--job", required=True)

    args = parser.parse_args()
    project_root, store = _resolve_roots(args)

    if args.command == "record-feedback":
        statement = args.provenance_statement or args.comment or "Feedback recorded."
        result = record_feedback(
            store=store,
            project_root=project_root,
            trace_path=Path(args.trace_path),
            trace_id=args.trace_id,
            feedback_type=FeedbackType(args.type),
            sentiment=Sentiment(args.sentiment),
            comment=args.comment,
            expected_answer=args.expected_answer,
            expected_sql=args.expected_sql,
            business_statements=args.business_statement,
            provenance=Provenance(
                provenance_type="user_declared_business_truth"
                if args.business_statement
                else "user_feedback",
                source_id=args.source_id,
                statement=statement,
            ),
            actor=Actor(
                actor_id=args.actor_id,
                actor_type=ActorType(args.actor_type),
                authority_status=AuthorityStatus.UNVERIFIED,
                authorized_context_ids=args.authorized_context_id,
                authorized_scopes=args.authorized_scope,
            ),
            supersedes_feedback_id=args.supersedes_feedback_id,
            allow_missing_trace=args.allow_missing_trace,
        )
        _print_json(
            {
                "feedback_id": result.feedback.feedback_id,
                "case_id": result.case.case_id if result.case else None,
                "case_created": result.case_created,
                "authority_status": result.feedback.actor.authority_status.value,
            },
            pretty=True,
        )
        return

    if args.command == "ingest-traces":
        summary = ingest_traces(
            store=store,
            trace_path=Path(args.trace_path),
            project_root=project_root,
        )
        _print_json(summary.to_dict(), pretty=True)
        return

    if args.command == "ingest-eval":
        summary = ingest_eval_run(
            store=store,
            run_path=Path(args.run_path),
            run_id=args.run_id,
            project_root=project_root,
            trace_path=Path(args.trace_path) if args.trace_path else None,
        )
        _print_json(summary.to_dict(), pretty=True)
        return

    if args.command == "list-cases":
        cases = store.list_cases(args.status)
        _print_json([case.to_dict() for case in cases], pretty=args.pretty)
        return

    if args.command == "show-case":
        _print_json(store.get_case(args.case).to_dict(), pretty=args.pretty)
        return

    if args.command == "report":
        cases = store.list_cases(args.status)
        report_path = store.write_report(new_report_id(), render_triage_report(cases))
        _print_json(
            {
                "case_count": len(cases),
                "report_path": report_path.relative_to(project_root).as_posix(),
            },
            pretty=True,
        )
        return

    if args.command == "record-authority":
        if not args.project_authority_confirmed:
            raise ValueError(
                "record-authority requires --project-authority-confirmed. "
                "The CLI records a project decision but does not authenticate the operator."
            )
        decision = record_authority_decision(
            store=store,
            feedback_id=args.feedback_id,
            decision=AuthorityDecisionType(args.decision),
            context_ids=args.context_id,
            scopes=args.scope,
            decided_by=args.decided_by,
            reason=args.reason,
            supersedes_authority_id=args.supersedes_authority_id,
        )
        _print_json(decision.to_dict(), pretty=True)
        return

    if args.command == "suggest-groups":
        _print_json(suggest_groups(store=store), pretty=True)
        return

    if args.command == "create-finding":
        finding = create_grouped_finding(
            store=store,
            context_id=args.context_id,
            grouping_mode=GroupingMode(args.grouping_mode),
            case_ids=args.case,
            root_cause_candidate=RootCauseCandidate(args.root_cause),
            business_truth_feedback_ids=args.business_feedback,
            business_scopes=args.business_scope,
        )
        _print_json(finding.to_dict(), pretty=True)
        return

    if args.command == "list-findings":
        findings = store.list_findings(args.status)
        _print_json([finding.to_dict() for finding in findings], pretty=args.pretty)
        return

    if args.command == "show-finding":
        _print_json(store.get_finding(args.finding).to_dict(), pretty=args.pretty)
        return

    if args.command == "dismiss-finding":
        finding = dismiss_finding(
            store=store,
            finding_id=args.finding,
            reviewer_id=args.reviewer_id,
            reason=args.reason,
        )
        _print_json(finding.to_dict(), pretty=True)
        return

    if args.command == "create-eval-target":
        target = create_eval_target(
            store=store,
            finding_id=args.finding,
            question=args.question,
            result_contract=ResultContract(
                expected_value=_parse_expected_value(args.expected_value),
                numeric_tolerance=args.numeric_tolerance,
            ),
            semantic_constraints=SemanticConstraints(
                required_filters=args.required_filter,
                required_units=args.required_unit,
                forbidden_units=args.forbidden_unit,
            ),
            sql_hints=args.sql_hint,
            evidence_refs=args.evidence_ref,
            supersedes_eval_target_id=args.supersedes_eval_target_id,
        )
        _print_json(target.to_dict(), pretty=True)
        return

    if args.command == "submit-eval-target":
        target = submit_eval_target_for_review(
            store=store,
            eval_target_id=args.eval_target,
        )
        _print_json(target.to_dict(), pretty=True)
        return

    if args.command == "approve-eval-target":
        target = approve_eval_target(
            store=store,
            eval_target_id=args.eval_target,
            reviewer_id=args.reviewer_id,
        )
        _print_json(target.to_dict(), pretty=True)
        return

    if args.command == "freeze-eval-target":
        target = freeze_eval_target(
            store=store,
            eval_target_id=args.eval_target,
        )
        _print_json(target.to_dict(), pretty=True)
        return

    if args.command == "invalidate-eval-target":
        target = mark_eval_target_terminal(
            store=store,
            eval_target_id=args.eval_target,
            target_status=EvalTargetStatus.INVALID,
            reason=args.reason,
        )
        _print_json(target.to_dict(), pretty=True)
        return

    if args.command == "list-eval-targets":
        targets = store.list_eval_targets(
            finding_id=args.finding,
            status=args.status,
        )
        _print_json([target.to_dict() for target in targets], pretty=args.pretty)
        return

    if args.command == "show-eval-target":
        _print_json(
            store.get_eval_target(args.eval_target).to_dict(),
            pretty=args.pretty,
        )
        return

    if args.command == "prepare-semantic-job":
        job = prepare_semantic_job(
            store=store,
            eval_target_id=args.eval_target,
            base_candidate_id=args.base_candidate_id,
            base_snapshot_path=Path(args.base_snapshot_path),
            data_identity={
                "schema_fingerprint": args.schema_fingerprint,
                "snapshot_id": args.snapshot_id,
            },
            risk_level=args.risk_level,
            target_eval_repetitions=args.target_repetitions,
            timeout_seconds=args.timeout_seconds,
            max_repair_rounds=args.max_repair_rounds,
        )
        _print_json(job.to_dict(), pretty=True)
        return

    if args.command == "execute-semantic-job":
        if not args.execute:
            raise ValueError("execute-semantic-job requires the explicit --execute flag.")
        from .codex_executor import ContextBuilderSemanticExecutor

        executor = ContextBuilderSemanticExecutor(
            project_root=project_root,
            context_registry_root=Path(args.context_registry_root),
            wren_home=Path(args.wren_home),
            wren_bin=Path(args.wren_bin),
            codex_bin=args.codex_bin,
            codex_model=args.codex_model,
            regression_suites=[Path(path) for path in args.regression_suite],
            smoke_sql=args.smoke_sql,
            eval_model=args.eval_model,
            eval_query_limit=args.eval_query_limit,
            eval_timeout_seconds=args.eval_timeout_seconds,
        )
        result = execute_semantic_job(
            store=store,
            job_id=args.job,
            executor=executor,
            external_isolation_confirmed=args.external_isolation_confirmed,
        )
        _print_json(result.to_dict(), pretty=True)
        return

    if args.command == "show-job":
        _print_json(store.get_job(args.job).to_dict(), pretty=args.pretty)
        return

    if args.command == "show-job-result":
        _print_json(store.get_job_result(args.job).to_dict(), pretty=args.pretty)
        return

    if args.command == "verify-job":
        job = store.get_job(args.job)
        error = verify_job_integrity(store=store, job=job)
        _print_json(
            {
                "job_id": job.job_id,
                "ok": error is None,
                "error": error,
            },
            pretty=True,
        )


def _resolve_roots(args: argparse.Namespace) -> tuple[Path, ImprovementStore]:
    project_root = Path(args.project_root).resolve()
    registry_arg = Path(args.registry_root)
    registry_root = (
        (project_root / registry_arg).resolve()
        if not registry_arg.is_absolute()
        else registry_arg.resolve()
    )
    try:
        registry_root.relative_to(project_root)
    except ValueError as exc:
        raise ValueError("registry-root must remain inside project-root.") from exc
    return project_root, ImprovementStore(registry_root)


def _enum_values(enum_type: type[Any]) -> list[str]:
    return [item.value for item in enum_type]


def _print_json(value: Any, *, pretty: bool) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2 if pretty else None))


def _parse_expected_value(value: str | None) -> str | int | float | bool | None:
    if value is None:
        return None
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return value
    if loaded is not None and not isinstance(loaded, (str, int, float, bool)):
        raise ValueError("expected-value must be a JSON scalar.")
    return loaded


def _configure_utf8_output() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    main()
