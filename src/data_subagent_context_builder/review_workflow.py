from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .revision_store import (
    CandidateStatus,
    HumanTaskType,
    InvalidTransitionError,
    ProvenanceType,
    RevisionStatus,
    RevisionStore,
)


def review_candidate(
    *,
    registry_root: Path,
    candidate_id: str,
    store: RevisionStore | None = None,
) -> dict[str, Any]:
    active_store = store or RevisionStore(registry_root)
    candidate = active_store.get_candidate(candidate_id)
    revision = active_store.get_revision(candidate.revision_id) if candidate.revision_id else None
    revision_dir = active_store.revision_dir(revision.revision_id) if revision else None
    return {
        "ok": True,
        "candidate": _candidate_summary(candidate),
        "revision": _revision_summary(revision) if revision else None,
        "review_packet": _load_optional_json(revision_dir / "review_packet.json")
        if revision_dir
        else None,
        "semantic_diff": _load_optional_json(revision_dir / "semantic_diff.json")
        if revision_dir
        else None,
        "human_tasks": [
            {
                "task_id": task.task_id,
                "task_type": task.task_type.value,
                "status": task.status.value,
                "questions": [
                    {
                        "question_id": question.question_id,
                        "prompt": question.prompt,
                        "rationale": question.rationale,
                    }
                    for question in task.questions
                ],
            }
            for task in active_store.list_human_tasks(revision.revision_id)
        ]
        if revision
        else [],
    }


def answer_review_question(
    *,
    registry_root: Path,
    revision_id: str,
    task_id: str,
    question_id: str,
    answer: str,
    store: RevisionStore | None = None,
) -> dict[str, Any]:
    active_store = store or RevisionStore(registry_root)
    revision = active_store.get_revision(revision_id)
    if revision.status != RevisionStatus.CLARIFICATION_REQUIRED:
        raise InvalidTransitionError(
            f"Revision {revision_id} is not waiting for clarification."
        )
    human_answer = active_store.answer_human_question(
        revision_id=revision_id,
        task_id=task_id,
        question_id=question_id,
        answer=answer,
        provenance_type=ProvenanceType.USER_DECLARED_BUSINESS_TRUTH,
    )
    task = active_store.get_human_task(revision_id, task_id)
    return {
        "ok": True,
        "revision_id": revision_id,
        "task_id": task_id,
        "question_id": question_id,
        "answer_id": human_answer.answer_id,
        "answer_provenance": human_answer.provenance.provenance_type.value,
        "task_status": task.status.value,
        "ready_to_resume": not any(
            item.status.value == "OPEN"
            for item in active_store.list_human_tasks(
                revision_id,
                task_type=HumanTaskType.CLARIFICATION,
            )
        ),
    }


def approve_candidate(
    *,
    registry_root: Path,
    candidate_id: str,
    approval_note: str,
    store: RevisionStore | None = None,
) -> dict[str, Any]:
    active_store = store or RevisionStore(registry_root)
    candidate = active_store.get_candidate(candidate_id)
    if candidate.status != CandidateStatus.REVIEW_REQUIRED or not candidate.revision_id:
        raise InvalidTransitionError(
            f"Candidate {candidate_id} must be REVIEW_REQUIRED before approval."
        )
    revision = active_store.get_revision(candidate.revision_id)
    if revision.status != RevisionStatus.REVIEW_REQUIRED:
        raise InvalidTransitionError(
            f"Revision {revision.revision_id} must be REVIEW_REQUIRED before approval."
        )
    review_packet_path = active_store.revision_dir(revision.revision_id) / "review_packet.json"
    if not review_packet_path.is_file():
        raise InvalidTransitionError("Candidate cannot be approved without a review packet.")
    task = active_store.create_human_task(
        revision_id=revision.revision_id,
        task_type=HumanTaskType.APPROVAL,
        questions=[
            (
                f"Approve candidate {candidate.candidate_id} version {candidate.version}?",
                "Publication requires an explicit human semantic-review decision.",
            )
        ],
    )
    answer = active_store.answer_human_question(
        revision_id=revision.revision_id,
        task_id=task.task_id,
        question_id=task.questions[0].question_id,
        answer=approval_note,
        provenance_type=ProvenanceType.USER_REVIEW_DECISION,
    )
    approved_revision = active_store.transition_revision(
        revision.revision_id,
        RevisionStatus.APPROVED,
        expected_status=RevisionStatus.REVIEW_REQUIRED,
    )
    approved_candidate = active_store.transition_candidate(
        candidate.candidate_id,
        CandidateStatus.APPROVED,
        expected_status=CandidateStatus.REVIEW_REQUIRED,
    )
    return {
        "ok": True,
        "candidate_id": candidate.candidate_id,
        "candidate_status": approved_candidate.status.value,
        "revision_id": revision.revision_id,
        "revision_status": approved_revision.status.value,
        "approval_task_id": task.task_id,
        "approval_answer_id": answer.answer_id,
        "approval_provenance": answer.provenance.provenance_type.value,
    }


def reject_candidate(
    *,
    registry_root: Path,
    candidate_id: str,
    reason: str,
    store: RevisionStore | None = None,
) -> dict[str, Any]:
    reason_text = reason.strip()
    if not reason_text:
        raise ValueError("Rejection reason must not be empty.")
    active_store = store or RevisionStore(registry_root)
    candidate = active_store.get_candidate(candidate_id)
    if not candidate.revision_id:
        raise InvalidTransitionError("Only revision candidates can use this rejection workflow.")
    revision = active_store.get_revision(candidate.revision_id)
    rejected_revision = active_store.transition_revision(
        revision.revision_id,
        RevisionStatus.REJECTED,
        expected_status=revision.status,
    )
    rejected_candidate = active_store.transition_candidate(
        candidate.candidate_id,
        CandidateStatus.REJECTED,
        expected_status=candidate.status,
    )
    rejection_path = active_store.revision_dir(revision.revision_id) / "rejection.json"
    rejection_path.write_text(
        json.dumps(
            {
                "candidate_id": candidate_id,
                "revision_id": revision.revision_id,
                "reason": reason_text,
                "provenance_type": ProvenanceType.USER_REVIEW_DECISION.value,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "ok": True,
        "candidate_id": candidate_id,
        "candidate_status": rejected_candidate.status.value,
        "revision_id": revision.revision_id,
        "revision_status": rejected_revision.status.value,
        "rejection_path": str(rejection_path),
    }


def publish_candidate(
    *,
    registry_root: Path,
    candidate_id: str,
    store: RevisionStore | None = None,
) -> dict[str, Any]:
    active_store = store or RevisionStore(registry_root)
    publication = active_store.publish_candidate(candidate_id)
    return {"ok": True, "publication": publication}


def rollback_context(
    *,
    registry_root: Path,
    context_id: str,
    target_candidate_id: str | None = None,
    store: RevisionStore | None = None,
) -> dict[str, Any]:
    active_store = store or RevisionStore(registry_root)
    publication = active_store.rollback_context(
        context_id,
        target_candidate_id=target_candidate_id,
    )
    return {"ok": True, "publication": publication}


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else None


def _candidate_summary(candidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "context_id": candidate.context_id,
        "version": candidate.version,
        "status": candidate.status.value,
        "project_path": candidate.project_path,
        "base_candidate_id": candidate.base_candidate_id,
        "revision_id": candidate.revision_id,
    }


def _revision_summary(revision) -> dict[str, Any]:
    return {
        "revision_id": revision.revision_id,
        "base_candidate_id": revision.base_candidate_id,
        "candidate_id": revision.candidate_id,
        "status": revision.status.value,
        "risk_level": revision.risk_level.value,
        "user_instruction": revision.user_instruction,
    }
