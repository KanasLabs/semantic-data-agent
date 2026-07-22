from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from .models import (
    ActorType,
    AuthorityDecision,
    AuthorityDecisionType,
    EvalTarget,
    EvalTargetStatus,
    FeedbackType,
    FindingStatus,
    GroupedFinding,
    GroupingMode,
    ResultContract,
    RootCauseCandidate,
    SemanticConstraints,
    TriageStatus,
    new_record_id,
)
from .store import ImprovementStore


_SEMANTIC_ROOT_CAUSES = {
    RootCauseCandidate.BUSINESS_SEMANTIC_GAP,
    RootCauseCandidate.SUMMARIZATION_GAP,
}
_SINGLETON_STRUCTURAL_ROOT_CAUSES = {
    RootCauseCandidate.CONTEXT_GAP,
    RootCauseCandidate.SQL_GUARDRAIL_DEFECT,
    RootCauseCandidate.WREN_RUNTIME_FAILURE,
    RootCauseCandidate.INFRASTRUCTURE_FAILURE,
}


def record_authority_decision(
    *,
    store: ImprovementStore,
    feedback_id: str,
    decision: AuthorityDecisionType,
    context_ids: list[str],
    scopes: list[str],
    decided_by: str,
    reason: str,
    supersedes_authority_id: str | None = None,
) -> AuthorityDecision:
    feedback = store.get_feedback(feedback_id)
    if decision == AuthorityDecisionType.CONFIRM and feedback.actor.actor_type not in {
        ActorType.BUSINESS_CONTRIBUTOR,
        ActorType.AUTHORIZED_BUSINESS_CONFIRMER,
    }:
        raise ValueError("Only a business contributor/ confirmer can receive authority.")
    normalized_contexts = _unique_text(context_ids)
    normalized_scopes = _unique_text(scopes)
    if decision == AuthorityDecisionType.CONFIRM:
        if supersedes_authority_id is not None:
            raise ValueError("CONFIRM decisions must not supersede another decision.")
    else:
        if supersedes_authority_id is None:
            raise ValueError("REVOKE decisions require supersedes_authority_id.")
        prior = store.get_authority_decision(supersedes_authority_id)
        if prior.feedback_id != feedback_id or prior.actor_id != feedback.actor.actor_id:
            raise ValueError("Revocation must reference a confirmation for the same feedback actor.")
        if prior.decision != AuthorityDecisionType.CONFIRM:
            raise ValueError("Only a CONFIRM authority decision can be revoked.")
        if any(
            item.decision == AuthorityDecisionType.REVOKE
            and item.supersedes_authority_id == prior.authority_id
            for item in store.list_authority_decisions(feedback_id)
        ):
            raise ValueError(f"Authority decision is already revoked: {prior.authority_id}")
        normalized_contexts = list(prior.context_ids)
        normalized_scopes = list(prior.scopes)
    authority = AuthorityDecision(
        schema_version=1,
        authority_id=new_record_id("authority"),
        feedback_id=feedback_id,
        actor_id=feedback.actor.actor_id,
        decision=decision,
        context_ids=normalized_contexts,
        scopes=normalized_scopes,
        decided_by=decided_by,
        reason=reason,
        created_at=_utc_now(),
        supersedes_authority_id=supersedes_authority_id,
    )
    store.create_authority_decision(authority)
    return authority


def effective_authority(
    *,
    store: ImprovementStore,
    feedback_id: str,
    context_id: str,
    required_scopes: list[str],
) -> AuthorityDecision | None:
    feedback = store.get_feedback(feedback_id)
    decisions = store.list_authority_decisions(feedback_id)
    revoked = {
        decision.supersedes_authority_id
        for decision in decisions
        if decision.decision == AuthorityDecisionType.REVOKE
    }
    required = set(required_scopes)
    confirmations = sorted(
        (
            decision
            for decision in decisions
            if decision.decision == AuthorityDecisionType.CONFIRM
            and decision.authority_id not in revoked
            and decision.actor_id == feedback.actor.actor_id
            and context_id in decision.context_ids
            and required.issubset(set(decision.scopes))
        ),
        key=lambda item: (item.created_at, item.authority_id),
        reverse=True,
    )
    return confirmations[0] if confirmations else None


def suggest_groups(
    *,
    store: ImprovementStore,
    triage_status: TriageStatus = TriageStatus.UNTRIAGED,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, tuple[str, ...]], list[str]] = {}
    active_case_ids = {
        case_id
        for finding in store.list_findings()
        if finding.status != FindingStatus.DISMISSED
        for case_id in finding.case_ids
    }
    for case in store.list_cases(triage_status.value):
        if case.case_id in active_case_ids:
            continue
        signature = (
            case.context_identity.context_id or "unknown",
            case.failure_phase.value,
            tuple(sorted(signal.signal_type for signal in case.signals)),
        )
        grouped.setdefault(signature, []).append(case.case_id)
    suggestions: list[dict[str, Any]] = []
    for signature, case_ids in sorted(grouped.items()):
        context_id, phase, signal_types = signature
        root_cause = _root_cause_for_phase(phase, signal_types)
        singleton_allowed = root_cause in _SINGLETON_STRUCTURAL_ROOT_CAUSES
        if len(case_ids) < 2 and not singleton_allowed:
            continue
        suggestions.append(
            {
                "context_id": context_id,
                "grouping_mode": (
                    GroupingMode.SINGLETON.value
                    if len(case_ids) == 1
                    else GroupingMode.CLUSTER.value
                ),
                "case_ids": sorted(case_ids),
                "root_cause_candidate": root_cause.value,
                "signature": {
                    "failure_phase": phase,
                    "signal_types": list(signal_types),
                },
            }
        )
    return suggestions


def create_grouped_finding(
    *,
    store: ImprovementStore,
    context_id: str,
    grouping_mode: GroupingMode,
    case_ids: list[str],
    root_cause_candidate: RootCauseCandidate,
    business_truth_feedback_ids: list[str] | None = None,
    business_scopes: list[str] | None = None,
) -> GroupedFinding:
    normalized_case_ids = list(dict.fromkeys(case_ids))
    active_findings = [
        finding
        for finding in store.list_findings()
        if finding.status != FindingStatus.DISMISSED
    ]
    already_grouped = {
        case_id
        for finding in active_findings
        for case_id in finding.case_ids
        if case_id in normalized_case_ids
    }
    if already_grouped:
        raise ValueError(
            f"Cases already belong to active findings: {sorted(already_grouped)}"
        )
    cases = [store.get_case(case_id) for case_id in normalized_case_ids]
    for case in cases:
        case_context = case.context_identity.context_id
        if case_context is not None and case_context != context_id:
            raise ValueError(
                f"Case {case.case_id} belongs to Context {case_context}, not {context_id}."
            )
    scopes = _unique_text(list(business_scopes or []))
    confirmed_feedback_ids: list[str] = []
    authority_decision_ids: list[str] = []
    for feedback_id in dict.fromkeys(business_truth_feedback_ids or []):
        feedback = store.get_feedback(feedback_id)
        pair = feedback.correction_pair
        statements = pair.expected.business_statements if pair is not None else []
        if feedback.feedback_type not in {
            FeedbackType.BUSINESS_TRUTH,
            FeedbackType.CORRECTION,
        } or not statements:
            raise ValueError(
                f"Feedback {feedback_id} is not correction-bearing business truth."
            )
        authority = effective_authority(
            store=store,
            feedback_id=feedback_id,
            context_id=context_id,
            required_scopes=scopes,
        )
        if authority is None:
            raise ValueError(
                f"Feedback {feedback_id} lacks project-confirmed authority for the Context/scope."
            )
        confirmed_feedback_ids.append(feedback_id)
        authority_decision_ids.append(authority.authority_id)

    if grouping_mode == GroupingMode.SINGLETON:
        if len(normalized_case_ids) != 1:
            raise ValueError("SINGLETON findings require exactly one case.")
        if root_cause_candidate in _SEMANTIC_ROOT_CAUSES:
            if not confirmed_feedback_ids or not scopes:
                raise ValueError(
                    "Semantic singleton findings require authorized business truth and scopes."
                )
        elif root_cause_candidate not in _SINGLETON_STRUCTURAL_ROOT_CAUSES:
            raise ValueError(
                "Singleton findings require authorized semantic truth or a structural failure."
            )
    elif len(normalized_case_ids) < 2:
        raise ValueError("CLUSTER findings require at least two cases.")

    if root_cause_candidate in _SEMANTIC_ROOT_CAUSES:
        if confirmed_feedback_ids and not scopes:
            raise ValueError("Confirmed semantic findings require explicit business scopes.")

    if root_cause_candidate in _SEMANTIC_ROOT_CAUSES:
        status = (
            FindingStatus.EVAL_TARGET_REQUIRED
            if confirmed_feedback_ids
            else FindingStatus.WAITING_FOR_BUSINESS_TRUTH
        )
    elif root_cause_candidate == RootCauseCandidate.EVAL_TARGET_QUALITY:
        status = FindingStatus.WAITING_FOR_BUSINESS_TRUTH
    else:
        status = FindingStatus.EVAL_TARGET_REQUIRED
    trace_ids = sorted(
        {
            case.source_identity.trace_id
            for case in cases
            if case.source_identity.trace_id is not None
        }
    )
    finding = GroupedFinding(
        schema_version=1,
        finding_id=new_record_id("finding"),
        context_id=context_id,
        grouping_mode=grouping_mode,
        case_ids=normalized_case_ids,
        representative_trace_ids=trace_ids,
        root_cause_candidate=root_cause_candidate,
        confirmed_business_truth_feedback_ids=confirmed_feedback_ids,
        authority_decision_ids=authority_decision_ids,
        business_scopes=scopes,
        status=status,
        created_at=_utc_now(),
    )
    store.create_finding(finding)
    return finding


def create_eval_target(
    *,
    store: ImprovementStore,
    finding_id: str,
    question: str,
    result_contract: ResultContract,
    semantic_constraints: SemanticConstraints,
    sql_hints: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    supersedes_eval_target_id: str | None = None,
) -> EvalTarget:
    finding = store.get_finding(finding_id)
    if finding.status != FindingStatus.EVAL_TARGET_REQUIRED:
        raise ValueError(
            f"Finding {finding_id} is {finding.status.value}, not EVAL_TARGET_REQUIRED."
        )
    existing = store.list_eval_targets(finding_id=finding_id)
    prior = None
    if supersedes_eval_target_id is not None:
        prior = store.get_eval_target(supersedes_eval_target_id)
        if prior.finding_id != finding_id:
            raise ValueError("A replacement EvalTarget must belong to the same finding.")
        if prior.status in {EvalTargetStatus.SUPERSEDED, EvalTargetStatus.INVALID}:
            raise ValueError("A replacement EvalTarget cannot supersede a terminal target.")
    target = EvalTarget(
        schema_version=1,
        eval_target_id=new_record_id("evaltarget"),
        version=max((item.version for item in existing), default=0) + 1,
        finding_id=finding_id,
        question=question,
        result_contract=result_contract,
        semantic_constraints=semantic_constraints,
        sql_hints=_unique_text(list(sql_hints or [])),
        evidence_refs=_unique_text(
            list(evidence_refs or [])
            + finding.case_ids
            + finding.confirmed_business_truth_feedback_ids
            + finding.authority_decision_ids
        ),
        frozen_sha256=None,
        status=EvalTargetStatus.DRAFT,
        created_at=_utc_now(),
        supersedes_eval_target_id=supersedes_eval_target_id,
    )
    store.create_eval_target(target)
    if supersedes_eval_target_id is not None:
        mark_eval_target_terminal(
            store=store,
            eval_target_id=supersedes_eval_target_id,
            target_status=EvalTargetStatus.SUPERSEDED,
            reason=f"Superseded by {target.eval_target_id}",
        )
    return target


def dismiss_finding(
    *,
    store: ImprovementStore,
    finding_id: str,
    reviewer_id: str,
    reason: str,
) -> GroupedFinding:
    finding = store.get_finding(finding_id)
    if finding.status == FindingStatus.DISMISSED:
        raise ValueError("Finding is already dismissed.")
    dismissed = replace(
        finding,
        status=FindingStatus.DISMISSED,
        dismissed_by=reviewer_id,
        dismissed_at=_utc_now(),
        terminal_reason=reason,
    )
    store.replace_finding(dismissed, expected_status=finding.status)
    return dismissed


def submit_eval_target_for_review(
    *,
    store: ImprovementStore,
    eval_target_id: str,
) -> EvalTarget:
    target = store.get_eval_target(eval_target_id)
    if target.status != EvalTargetStatus.DRAFT:
        raise ValueError("Only DRAFT EvalTargets can be submitted for review.")
    updated = replace(target, status=EvalTargetStatus.NEEDS_BUSINESS_REVIEW)
    store.replace_eval_target(updated, expected_status=EvalTargetStatus.DRAFT)
    return updated


def approve_eval_target(
    *,
    store: ImprovementStore,
    eval_target_id: str,
    reviewer_id: str,
) -> EvalTarget:
    target = store.get_eval_target(eval_target_id)
    if target.status != EvalTargetStatus.NEEDS_BUSINESS_REVIEW:
        raise ValueError("Only targets awaiting business review can be approved.")
    finding = store.get_finding(target.finding_id)
    require_finding_authority(store, finding)
    updated = replace(
        target,
        status=EvalTargetStatus.APPROVED,
        reviewed_by=reviewer_id,
        approved_at=_utc_now(),
    )
    store.replace_eval_target(
        updated,
        expected_status=EvalTargetStatus.NEEDS_BUSINESS_REVIEW,
    )
    return updated


def freeze_eval_target(
    *,
    store: ImprovementStore,
    eval_target_id: str,
) -> EvalTarget:
    target = store.get_eval_target(eval_target_id)
    if target.status != EvalTargetStatus.APPROVED:
        raise ValueError("Only APPROVED EvalTargets can be frozen.")
    require_finding_authority(store, store.get_finding(target.finding_id))
    frozen_at = _utc_now()
    updated = replace(
        target,
        status=EvalTargetStatus.FROZEN,
        frozen_sha256=eval_target_content_sha256(target),
        frozen_at=frozen_at,
    )
    store.replace_eval_target(updated, expected_status=EvalTargetStatus.APPROVED)
    return updated


def mark_eval_target_terminal(
    *,
    store: ImprovementStore,
    eval_target_id: str,
    target_status: EvalTargetStatus,
    reason: str,
) -> EvalTarget:
    if target_status not in {EvalTargetStatus.INVALID, EvalTargetStatus.SUPERSEDED}:
        raise ValueError("Terminal EvalTarget status must be INVALID or SUPERSEDED.")
    target = store.get_eval_target(eval_target_id)
    if target.status in {EvalTargetStatus.INVALID, EvalTargetStatus.SUPERSEDED}:
        raise ValueError(f"EvalTarget is already terminal: {target.status.value}")
    updated = replace(target, status=target_status, terminal_reason=reason)
    store.replace_eval_target(updated, expected_status=target.status)
    return updated


def eval_target_content_sha256(target: EvalTarget) -> str:
    payload = {
        "schema_version": target.schema_version,
        "eval_target_id": target.eval_target_id,
        "version": target.version,
        "finding_id": target.finding_id,
        "question": target.question,
        "result_contract": {
            "expected_value": target.result_contract.expected_value,
            "numeric_tolerance": target.result_contract.numeric_tolerance,
        },
        "semantic_constraints": {
            "required_filters": target.semantic_constraints.required_filters,
            "required_units": target.semantic_constraints.required_units,
            "forbidden_units": target.semantic_constraints.forbidden_units,
        },
        "sql_hints": target.sql_hints,
        "evidence_refs": target.evidence_refs,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _root_cause_for_phase(
    phase: str,
    signal_types: tuple[str, ...],
) -> RootCauseCandidate:
    if "EVAL_NEEDS_TRIAGE" in signal_types:
        return RootCauseCandidate.EVAL_TARGET_QUALITY
    mapping = {
        "CONTEXT": RootCauseCandidate.CONTEXT_GAP,
        "SQL_GENERATION": RootCauseCandidate.SQL_GENERATION_DEFECT,
        "SQL_GUARDRAIL": RootCauseCandidate.SQL_GUARDRAIL_DEFECT,
        "WREN_DRY_PLAN": RootCauseCandidate.WREN_RUNTIME_FAILURE,
        "WREN_DRY_RUN": RootCauseCandidate.WREN_RUNTIME_FAILURE,
        "EXECUTION": RootCauseCandidate.EXECUTION_FAILURE,
        "SUMMARIZATION": RootCauseCandidate.SUMMARIZATION_GAP,
        "EVAL_ASSERTION": RootCauseCandidate.BUSINESS_SEMANTIC_GAP,
        "USER_FEEDBACK": RootCauseCandidate.BUSINESS_SEMANTIC_GAP,
    }
    return mapping.get(phase, RootCauseCandidate.UNKNOWN)


def require_finding_authority(
    store: ImprovementStore,
    finding: GroupedFinding,
) -> None:
    if finding.root_cause_candidate not in _SEMANTIC_ROOT_CAUSES:
        return
    if not finding.confirmed_business_truth_feedback_ids:
        raise ValueError("Semantic EvalTargets require confirmed business truth.")
    for feedback_id in finding.confirmed_business_truth_feedback_ids:
        if effective_authority(
            store=store,
            feedback_id=feedback_id,
            context_id=finding.context_id,
            required_scopes=finding.business_scopes,
        ) is None:
            raise ValueError(
                f"Authority was revoked or is missing for feedback {feedback_id}."
            )


def _unique_text(values: list[str]) -> list[str]:
    normalized = []
    for value in values:
        item = value.strip()
        if not item:
            raise ValueError("List values must not be empty.")
        if item not in normalized:
            normalized.append(item)
    return normalized


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
