from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from .models import (
    EvalTargetStatus,
    JobTargetType,
    RootCauseCandidate,
    RoutingDecision,
    RoutingEvidence,
    RoutingEvidenceType,
    RoutingProposal,
    RoutingProposalStatus,
    new_record_id,
)
from .store import ImprovementStore, ImprovementStoreError


_SEMANTIC_LAYER_JUSTIFICATION_EVIDENCE = {
    RoutingEvidenceType.CONTEXT_RULE_VERIFIED,
    RoutingEvidenceType.GENERATED_SQL_VERIFIED,
    RoutingEvidenceType.SOURCE_CONTRACT_OWNERSHIP_VERIFIED,
}

_SOURCE_FAILURE_EVIDENCE = {
    RoutingEvidenceType.SOURCE_REPRODUCTION,
    RoutingEvidenceType.POST_CONTEXT_FAILURE,
    RoutingEvidenceType.STRUCTURAL_SOURCE_DEFECT,
}

_SEMANTIC_OR_AMBIGUOUS_ROOT_CAUSES = {
    RootCauseCandidate.BUSINESS_SEMANTIC_GAP,
    RootCauseCandidate.CONTEXT_GAP,
    RootCauseCandidate.SQL_GENERATION_DEFECT,
    RootCauseCandidate.SUMMARIZATION_GAP,
    RootCauseCandidate.UNKNOWN,
}

ROUTING_VALIDATION_POLICY = "routing-gate-v1"


def create_routing_proposal(
    *,
    store: ImprovementStore,
    eval_target_id: str,
    proposed_target_type: JobTargetType,
    evidence: list[RoutingEvidence],
    proposed_by: str,
    rationale: str,
) -> RoutingProposal:
    target = store.get_eval_target(eval_target_id)
    finding = store.get_finding(target.finding_id)
    validation_errors = routing_validation_errors(
        target_type=proposed_target_type,
        evidence=evidence,
        target_status=target.status,
        target_finding_id=target.finding_id,
        decision_finding_id=finding.finding_id,
        root_cause_candidate=finding.root_cause_candidate,
    )
    proposal = RoutingProposal(
        schema_version=1,
        routing_proposal_id=new_record_id("routeproposal"),
        finding_id=finding.finding_id,
        eval_target_id=target.eval_target_id,
        proposed_target_type=proposed_target_type,
        evidence=list(evidence),
        proposed_by=proposed_by,
        rationale=rationale,
        status=(
            RoutingProposalStatus.DIAGNOSIS_REQUIRED
            if validation_errors
            else RoutingProposalStatus.READY_FOR_REVIEW
        ),
        validation_policy=ROUTING_VALIDATION_POLICY,
        validation_errors=validation_errors,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.create_routing_proposal(proposal)
    return proposal


def confirm_routing_proposal(
    *,
    store: ImprovementStore,
    routing_proposal_id: str,
    confirmed_by: str,
    rationale: str,
) -> RoutingDecision:
    proposal = store.get_routing_proposal(routing_proposal_id)
    if proposal.status != RoutingProposalStatus.READY_FOR_REVIEW:
        raise ValueError(
            "Only a READY_FOR_REVIEW RoutingProposal can be confirmed."
        )
    if proposal.validation_policy != ROUTING_VALIDATION_POLICY:
        raise ValueError("RoutingProposal validation policy is unsupported or stale.")
    target = store.get_eval_target(proposal.eval_target_id)
    finding = store.get_finding(proposal.finding_id)
    errors = routing_validation_errors(
        target_type=proposal.proposed_target_type,
        evidence=proposal.evidence,
        target_status=target.status,
        target_finding_id=target.finding_id,
        decision_finding_id=proposal.finding_id,
        root_cause_candidate=finding.root_cause_candidate,
    )
    if errors or proposal.validation_errors != errors:
        raise ValueError(
            "RoutingProposal no longer satisfies deterministic routing validation: "
            + "; ".join(errors or ["stored validation result changed"])
        )
    decision = RoutingDecision(
        schema_version=1,
        routing_decision_id=new_record_id("routing"),
        finding_id=proposal.finding_id,
        eval_target_id=proposal.eval_target_id,
        target_type=proposal.proposed_target_type,
        evidence=list(proposal.evidence),
        decided_by=confirmed_by,
        rationale=rationale,
        created_at=datetime.now(timezone.utc).isoformat(),
        routing_proposal_id=proposal.routing_proposal_id,
        routing_proposal_sha256=routing_proposal_sha256(proposal),
    )
    store.create_routing_decision(decision)
    return decision


def create_routing_decision(
    *,
    store: ImprovementStore,
    eval_target_id: str,
    target_type: JobTargetType,
    evidence: list[RoutingEvidence],
    decided_by: str,
    rationale: str,
) -> RoutingDecision:
    target = store.get_eval_target(eval_target_id)
    finding = store.get_finding(target.finding_id)
    decision = RoutingDecision(
        schema_version=1,
        routing_decision_id=new_record_id("routing"),
        finding_id=finding.finding_id,
        eval_target_id=target.eval_target_id,
        target_type=target_type,
        evidence=list(evidence),
        decided_by=decided_by,
        rationale=rationale,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    validate_routing_decision(
        decision=decision,
        target_status=target.status,
        target_finding_id=target.finding_id,
        root_cause_candidate=finding.root_cause_candidate,
    )
    store.create_routing_decision(decision)
    return decision


def require_source_routing_decision(
    *,
    store: ImprovementStore,
    routing_decision_id: str,
    finding_id: str,
    eval_target_id: str,
) -> RoutingDecision:
    return require_routing_decision(
        store=store,
        routing_decision_id=routing_decision_id,
        finding_id=finding_id,
        eval_target_id=eval_target_id,
        expected_target_type=JobTargetType.SOURCE_CODE,
    )


def require_routing_decision(
    *,
    store: ImprovementStore,
    routing_decision_id: str,
    finding_id: str,
    eval_target_id: str,
    expected_target_type: JobTargetType,
) -> RoutingDecision:
    try:
        decision = store.get_routing_decision(routing_decision_id)
        target = store.get_eval_target(eval_target_id)
        finding = store.get_finding(finding_id)
    except ImprovementStoreError as exc:
        raise ValueError(f"RoutingDecision is unavailable: {exc}") from exc
    if decision.finding_id != finding_id:
        raise ValueError("RoutingDecision finding does not match the Job finding.")
    if decision.eval_target_id != eval_target_id:
        raise ValueError("RoutingDecision EvalTarget does not match the Job target.")
    validate_routing_decision(
        decision=decision,
        target_status=target.status,
        target_finding_id=target.finding_id,
        root_cause_candidate=finding.root_cause_candidate,
    )
    verify_routing_decision_proposal(store=store, decision=decision)
    if decision.target_type != expected_target_type:
        phase = "SI3" if expected_target_type == JobTargetType.SOURCE_CODE else "SI2"
        raise ValueError(
            f"{phase} requires a {expected_target_type.value} RoutingDecision."
        )
    return decision


def validate_routing_decision(
    *,
    decision: RoutingDecision,
    target_status: EvalTargetStatus,
    target_finding_id: str,
    root_cause_candidate: RootCauseCandidate,
) -> None:
    errors = routing_validation_errors(
        target_type=decision.target_type,
        evidence=decision.evidence,
        target_status=target_status,
        target_finding_id=target_finding_id,
        decision_finding_id=decision.finding_id,
        root_cause_candidate=root_cause_candidate,
    )
    if errors:
        raise ValueError(errors[0])


def routing_validation_errors(
    *,
    target_type: JobTargetType,
    evidence: list[RoutingEvidence],
    target_status: EvalTargetStatus,
    target_finding_id: str,
    decision_finding_id: str,
    root_cause_candidate: RootCauseCandidate,
) -> list[str]:
    errors: list[str] = []
    if target_status != EvalTargetStatus.FROZEN:
        errors.append("RoutingDecision requires a FROZEN EvalTarget.")
    if decision_finding_id != target_finding_id:
        errors.append("RoutingDecision finding does not match its EvalTarget.")
    if target_type != JobTargetType.SOURCE_CODE:
        return errors
    if root_cause_candidate == RootCauseCandidate.EVAL_TARGET_QUALITY:
        errors.append(
            "EVAL_TARGET_QUALITY must be resolved by revising the EvalTarget, not SI3."
        )
    evidence_types = {item.evidence_type for item in evidence}
    if not evidence_types.intersection(_SOURCE_FAILURE_EVIDENCE):
        errors.append(
            "SOURCE_CODE routing requires source reproduction, post-Context failure, "
            "or structural source-defect evidence."
        )
    if (
        root_cause_candidate in _SEMANTIC_OR_AMBIGUOUS_ROOT_CAUSES
        and not evidence_types.intersection(_SEMANTIC_LAYER_JUSTIFICATION_EVIDENCE)
    ):
        errors.append(
            "Semantic or ambiguous findings require evidence that Context rules or "
            "generated SQL are already correct, or that the reviewed source contract "
            "explicitly owns the behavior, before SI3."
        )
    return errors


def verify_routing_decision_proposal(
    *,
    store: ImprovementStore,
    decision: RoutingDecision,
) -> None:
    if decision.routing_proposal_id is None:
        return
    try:
        proposal = store.get_routing_proposal(decision.routing_proposal_id)
    except ImprovementStoreError as exc:
        raise ValueError(f"RoutingProposal is unavailable: {exc}") from exc
    if routing_proposal_sha256(proposal) != decision.routing_proposal_sha256:
        raise ValueError("RoutingProposal content/hash changed after confirmation.")
    if proposal.status != RoutingProposalStatus.READY_FOR_REVIEW:
        raise ValueError("Confirmed RoutingProposal is not READY_FOR_REVIEW.")
    if (
        proposal.finding_id != decision.finding_id
        or proposal.eval_target_id != decision.eval_target_id
        or proposal.proposed_target_type != decision.target_type
        or proposal.evidence != decision.evidence
    ):
        raise ValueError("RoutingDecision does not match its confirmed RoutingProposal.")


def routing_decision_sha256(decision: RoutingDecision) -> str:
    payload = json.dumps(
        decision.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def routing_proposal_sha256(proposal: RoutingProposal) -> str:
    payload = json.dumps(
        proposal.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"
