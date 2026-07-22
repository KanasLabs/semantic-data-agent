from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class RevisionStoreError(RuntimeError):
    """Base error for revision registry operations."""


class InvalidTransitionError(RevisionStoreError):
    """Raised when a lifecycle transition is not allowed."""


class StaleBaseVersionError(RevisionStoreError):
    """Raised when a revision no longer targets the expected candidate state."""


class RecordNotFoundError(RevisionStoreError):
    """Raised when a requested registry record does not exist."""


class CandidateStatus(str, Enum):
    DRAFT = "DRAFT"
    AUTO_VALIDATING = "AUTO_VALIDATING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    SMOKE_FAILED = "SMOKE_FAILED"
    REJECTED = "REJECTED"
    STALE = "STALE"


class RevisionStatus(str, Enum):
    REVISION_REQUESTED = "REVISION_REQUESTED"
    REVISING = "REVISING"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    AUTO_VALIDATING = "AUTO_VALIDATING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    APPROVED = "APPROVED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    SMOKE_FAILED = "SMOKE_FAILED"
    REJECTED = "REJECTED"
    STALE = "STALE"


class HumanTaskType(str, Enum):
    CLARIFICATION = "CLARIFICATION"
    APPROVAL = "APPROVAL"


class HumanTaskStatus(str, Enum):
    OPEN = "OPEN"
    ANSWERED = "ANSWERED"
    CANCELLED = "CANCELLED"


class ProvenanceType(str, Enum):
    DATABASE_EVIDENCE = "database_evidence"
    EXISTING_CONTEXT = "existing_context"
    USER_DECLARED_BUSINESS_TRUTH = "user_declared_business_truth"
    USER_REVIEW_DECISION = "user_review_decision"
    CODEX_INFERENCE = "codex_inference"
    AUTOMATED_VALIDATION = "automated_validation"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


_CANDIDATE_TRANSITIONS = {
    CandidateStatus.DRAFT: {
        CandidateStatus.AUTO_VALIDATING,
        CandidateStatus.REJECTED,
        CandidateStatus.STALE,
    },
    CandidateStatus.AUTO_VALIDATING: {
        CandidateStatus.REVIEW_REQUIRED,
        CandidateStatus.VALIDATION_FAILED,
        CandidateStatus.SMOKE_FAILED,
    },
    CandidateStatus.REVIEW_REQUIRED: {
        CandidateStatus.APPROVED,
        CandidateStatus.REJECTED,
        CandidateStatus.STALE,
    },
    CandidateStatus.APPROVED: {
        CandidateStatus.PUBLISHED,
        CandidateStatus.STALE,
    },
    CandidateStatus.VALIDATION_FAILED: {
        CandidateStatus.AUTO_VALIDATING,
        CandidateStatus.REJECTED,
        CandidateStatus.STALE,
    },
    CandidateStatus.SMOKE_FAILED: {
        CandidateStatus.AUTO_VALIDATING,
        CandidateStatus.REJECTED,
        CandidateStatus.STALE,
    },
    CandidateStatus.PUBLISHED: set(),
    CandidateStatus.REJECTED: set(),
    CandidateStatus.STALE: set(),
}


_REVISION_TRANSITIONS = {
    RevisionStatus.REVISION_REQUESTED: {
        RevisionStatus.REVISING,
        RevisionStatus.CLARIFICATION_REQUIRED,
        RevisionStatus.REJECTED,
        RevisionStatus.STALE,
    },
    RevisionStatus.REVISING: {
        RevisionStatus.CLARIFICATION_REQUIRED,
        RevisionStatus.AUTO_VALIDATING,
        RevisionStatus.REJECTED,
        RevisionStatus.STALE,
    },
    RevisionStatus.CLARIFICATION_REQUIRED: {
        RevisionStatus.REVISING,
        RevisionStatus.REJECTED,
        RevisionStatus.STALE,
    },
    RevisionStatus.AUTO_VALIDATING: {
        RevisionStatus.REVIEW_REQUIRED,
        RevisionStatus.VALIDATION_FAILED,
        RevisionStatus.SMOKE_FAILED,
    },
    RevisionStatus.REVIEW_REQUIRED: {
        RevisionStatus.APPROVED,
        RevisionStatus.CHANGES_REQUESTED,
        RevisionStatus.REJECTED,
        RevisionStatus.STALE,
    },
    RevisionStatus.CHANGES_REQUESTED: {
        RevisionStatus.REVISING,
        RevisionStatus.CLARIFICATION_REQUIRED,
        RevisionStatus.REJECTED,
        RevisionStatus.STALE,
    },
    RevisionStatus.VALIDATION_FAILED: {
        RevisionStatus.REVISING,
        RevisionStatus.REJECTED,
        RevisionStatus.STALE,
    },
    RevisionStatus.SMOKE_FAILED: {
        RevisionStatus.REVISING,
        RevisionStatus.REJECTED,
        RevisionStatus.STALE,
    },
    RevisionStatus.APPROVED: set(),
    RevisionStatus.REJECTED: set(),
    RevisionStatus.STALE: set(),
}


@dataclass(frozen=True)
class Provenance:
    provenance_type: ProvenanceType
    source_id: str
    statement: str
    recorded_at: str = field(default_factory=lambda: _utc_now())


@dataclass
class CandidateRecord:
    candidate_id: str
    context_id: str
    version: int
    project_path: str
    status: CandidateStatus
    base_candidate_id: str | None
    created_at: str
    updated_at: str
    revision_id: str | None = None
    provenance: list[Provenance] = field(default_factory=list)
    release_eligible: bool = True


@dataclass
class ChangeRequest:
    revision_id: str
    base_candidate_id: str
    base_candidate_version: int
    candidate_id: str
    user_instruction: str
    requested_scope: list[str]
    provenance: Provenance
    risk_level: RiskLevel
    status: RevisionStatus
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class HumanQuestion:
    question_id: str
    prompt: str
    rationale: str
    required: bool = True


@dataclass
class HumanTask:
    task_id: str
    revision_id: str
    task_type: HumanTaskType
    status: HumanTaskStatus
    questions: list[HumanQuestion]
    created_at: str
    resolved_at: str | None = None


@dataclass(frozen=True)
class HumanAnswer:
    answer_id: str
    revision_id: str
    task_id: str
    question_id: str
    answer: str
    provenance: Provenance
    created_at: str


@dataclass
class SemanticDiff:
    revision_id: str
    base_candidate_id: str
    candidate_id: str
    models: list[dict[str, Any]] = field(default_factory=list)
    fields: list[dict[str, Any]] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    rules: list[dict[str, Any]] = field(default_factory=list)
    sql_examples: list[dict[str, Any]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    test_coverage: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ReviewPacket:
    revision_id: str
    candidate_id: str
    status: RevisionStatus
    summary: str
    semantic_diff: dict[str, Any] = field(default_factory=dict)
    provenance: list[Provenance] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)
    smoke_eval: dict[str, Any] = field(default_factory=dict)
    regression_eval: dict[str, Any] = field(default_factory=dict)
    open_questions: list[HumanQuestion] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: _utc_now())


class RevisionStore:
    def __init__(self, registry_root: Path) -> None:
        self.registry_root = registry_root.resolve()

    def create_candidate(
        self,
        *,
        context_id: str,
        project_path: Path | None = None,
        version: int = 1,
        base_candidate_id: str | None = None,
        revision_id: str | None = None,
        provenance: list[Provenance] | None = None,
        release_eligible: bool = True,
    ) -> CandidateRecord:
        _validate_identifier("context_id", context_id)
        if version < 1:
            raise ValueError("Candidate version must be at least 1.")
        candidate_id = _new_id("candidate")
        resolved_project_path = (
            project_path.resolve()
            if project_path is not None
            else self.candidate_dir(candidate_id) / "wren_project"
        )
        now = _utc_now()
        record = CandidateRecord(
            candidate_id=candidate_id,
            context_id=context_id,
            version=version,
            project_path=str(resolved_project_path),
            status=CandidateStatus.DRAFT,
            base_candidate_id=base_candidate_id,
            revision_id=revision_id,
            provenance=list(provenance or []),
            release_eligible=release_eligible,
            created_at=now,
            updated_at=now,
        )
        self._write_json(self._candidate_path(candidate_id), record)
        return record

    def get_candidate(self, candidate_id: str) -> CandidateRecord:
        data = self._read_json(self._candidate_path(candidate_id))
        return _candidate_from_dict(data)

    def transition_candidate(
        self,
        candidate_id: str,
        target: CandidateStatus,
        *,
        expected_status: CandidateStatus | None = None,
    ) -> CandidateRecord:
        record = self.get_candidate(candidate_id)
        if expected_status is not None and record.status != expected_status:
            raise StaleBaseVersionError(
                f"Candidate {candidate_id} is {record.status.value}, expected {expected_status.value}."
            )
        if target in {CandidateStatus.APPROVED, CandidateStatus.PUBLISHED} and not record.release_eligible:
            raise InvalidTransitionError(
                f"Candidate {candidate_id} is development-only and not release eligible."
            )
        if (
            record.status == CandidateStatus.REVIEW_REQUIRED
            and target == CandidateStatus.APPROVED
            and record.revision_id is not None
            and self.get_revision(record.revision_id).status != RevisionStatus.APPROVED
        ):
            raise InvalidTransitionError(
                f"Candidate {candidate_id} requires an approved revision before approval."
            )
        _require_transition("candidate", record.status, target, _CANDIDATE_TRANSITIONS)
        record.status = target
        record.updated_at = _utc_now()
        self._write_json(self._candidate_path(candidate_id), record)
        return record

    def create_revision(
        self,
        *,
        base_candidate_id: str,
        expected_base_version: int | None = None,
        user_instruction: str,
        requested_scope: list[str] | None = None,
        risk_level: RiskLevel = RiskLevel.MEDIUM,
        candidate_project_path: Path | None = None,
        release_eligible: bool = True,
    ) -> tuple[ChangeRequest, CandidateRecord]:
        instruction = user_instruction.strip()
        if not instruction:
            raise ValueError("User instruction must not be empty.")
        base = self.get_candidate(base_candidate_id)
        if expected_base_version is not None and base.version != expected_base_version:
            raise StaleBaseVersionError(
                f"Candidate {base_candidate_id} is version {base.version}, "
                f"expected version {expected_base_version}."
            )
        if base.status == CandidateStatus.PUBLISHED:
            pass
        elif base.status not in {CandidateStatus.DRAFT, CandidateStatus.REVIEW_REQUIRED, CandidateStatus.APPROVED}:
            raise StaleBaseVersionError(
                f"Candidate {base_candidate_id} cannot be revised from {base.status.value}."
            )
        revision_id = _new_id("revision")
        provenance = Provenance(
            provenance_type=ProvenanceType.USER_DECLARED_BUSINESS_TRUTH,
            source_id=revision_id,
            statement=instruction,
        )
        candidate = self.create_candidate(
            context_id=base.context_id,
            project_path=candidate_project_path,
            version=base.version + 1,
            base_candidate_id=base.candidate_id,
            revision_id=revision_id,
            provenance=[provenance],
            release_eligible=release_eligible,
        )
        now = _utc_now()
        request = ChangeRequest(
            revision_id=revision_id,
            base_candidate_id=base.candidate_id,
            base_candidate_version=base.version,
            candidate_id=candidate.candidate_id,
            user_instruction=instruction,
            requested_scope=list(requested_scope or []),
            provenance=provenance,
            risk_level=risk_level,
            status=RevisionStatus.REVISION_REQUESTED,
            created_at=now,
            updated_at=now,
        )
        self._write_json(self._change_request_path(revision_id), request)
        return request, candidate

    def get_revision(self, revision_id: str) -> ChangeRequest:
        return _change_request_from_dict(self._read_json(self._change_request_path(revision_id)))

    def transition_revision(
        self,
        revision_id: str,
        target: RevisionStatus,
        *,
        expected_status: RevisionStatus | None = None,
    ) -> ChangeRequest:
        request = self.get_revision(revision_id)
        if expected_status is not None and request.status != expected_status:
            raise StaleBaseVersionError(
                f"Revision {revision_id} is {request.status.value}, expected {expected_status.value}."
            )
        if (
            request.status == RevisionStatus.CLARIFICATION_REQUIRED
            and target == RevisionStatus.REVISING
            and self._has_open_task(revision_id, HumanTaskType.CLARIFICATION)
        ):
            raise InvalidTransitionError(
                f"Revision {revision_id} has unanswered clarification questions."
            )
        if (
            request.status == RevisionStatus.REVIEW_REQUIRED
            and target == RevisionStatus.APPROVED
            and not self._has_answered_task(revision_id, HumanTaskType.APPROVAL)
        ):
            raise InvalidTransitionError(
                f"Revision {revision_id} requires a completed approval task."
            )
        if target == RevisionStatus.APPROVED:
            candidate = self.get_candidate(request.candidate_id)
            if not candidate.release_eligible:
                raise InvalidTransitionError(
                    f"Candidate {candidate.candidate_id} is development-only and not release eligible."
                )
        _require_transition("revision", request.status, target, _REVISION_TRANSITIONS)
        request.status = target
        request.updated_at = _utc_now()
        self._write_json(self._change_request_path(revision_id), request)
        return request

    def create_human_task(
        self,
        *,
        revision_id: str,
        task_type: HumanTaskType,
        questions: list[tuple[str, str]],
    ) -> HumanTask:
        request = self.get_revision(revision_id)
        if task_type == HumanTaskType.CLARIFICATION:
            if request.status != RevisionStatus.CLARIFICATION_REQUIRED:
                raise InvalidTransitionError(
                    "Clarification tasks require revision status CLARIFICATION_REQUIRED."
                )
        elif request.status != RevisionStatus.REVIEW_REQUIRED:
            raise InvalidTransitionError("Approval tasks require revision status REVIEW_REQUIRED.")
        if not questions:
            raise ValueError("Human task must contain at least one question.")
        normalized_questions = []
        for prompt, rationale in questions:
            prompt_text = prompt.strip()
            rationale_text = rationale.strip()
            if not prompt_text or not rationale_text:
                raise ValueError("Human task questions require a prompt and rationale.")
            normalized_questions.append((prompt_text, rationale_text))
        task_id = _new_id("task")
        task = HumanTask(
            task_id=task_id,
            revision_id=revision_id,
            task_type=task_type,
            status=HumanTaskStatus.OPEN,
            questions=[
                HumanQuestion(question_id=_new_id("question"), prompt=prompt, rationale=rationale)
                for prompt, rationale in normalized_questions
            ],
            created_at=_utc_now(),
        )
        self._write_json(self._human_task_path(revision_id, task_id), task)
        return task

    def get_human_task(self, revision_id: str, task_id: str) -> HumanTask:
        return _human_task_from_dict(self._read_json(self._human_task_path(revision_id, task_id)))

    def answer_human_question(
        self,
        *,
        revision_id: str,
        task_id: str,
        question_id: str,
        answer: str,
        provenance_type: ProvenanceType = ProvenanceType.USER_DECLARED_BUSINESS_TRUTH,
    ) -> HumanAnswer:
        answer_text = answer.strip()
        if not answer_text:
            raise ValueError("Human answer must not be empty.")
        task = self.get_human_task(revision_id, task_id)
        if task.status != HumanTaskStatus.OPEN:
            raise InvalidTransitionError(f"Human task {task_id} is not open.")
        if question_id not in {question.question_id for question in task.questions}:
            raise RecordNotFoundError(f"Question {question_id} does not belong to task {task_id}.")
        if self._has_answer(task, question_id):
            raise InvalidTransitionError(f"Question {question_id} has already been answered.")
        answer_id = _new_id("answer")
        provenance = Provenance(
            provenance_type=provenance_type,
            source_id=answer_id,
            statement=answer_text,
        )
        human_answer = HumanAnswer(
            answer_id=answer_id,
            revision_id=revision_id,
            task_id=task_id,
            question_id=question_id,
            answer=answer_text,
            provenance=provenance,
            created_at=_utc_now(),
        )
        self._write_json(self._answer_path(revision_id, answer_id), human_answer)
        if self._all_questions_answered(task):
            task.status = HumanTaskStatus.ANSWERED
            task.resolved_at = _utc_now()
            self._write_json(self._human_task_path(revision_id, task_id), task)
        return human_answer

    def list_human_tasks(
        self,
        revision_id: str,
        *,
        task_type: HumanTaskType | None = None,
    ) -> list[HumanTask]:
        tasks_dir = self._revision_dir(revision_id) / "human_tasks"
        tasks = [
            _human_task_from_dict(self._read_json(path))
            for path in sorted(tasks_dir.glob("*.json"))
        ]
        if task_type is not None:
            tasks = [task for task in tasks if task.task_type == task_type]
        return tasks

    def list_human_answers(
        self,
        revision_id: str,
        *,
        task_id: str | None = None,
    ) -> list[HumanAnswer]:
        answers = [
            _human_answer_from_dict(self._read_json(path))
            for path in sorted(self._answers_dir(revision_id).glob("*.json"))
        ]
        if task_id is not None:
            answers = [answer for answer in answers if answer.task_id == task_id]
        return sorted(answers, key=lambda answer: answer.created_at)

    def write_semantic_diff(self, diff: SemanticDiff) -> Path:
        self.get_revision(diff.revision_id)
        path = self._revision_dir(diff.revision_id) / "semantic_diff.json"
        self._write_json(path, diff)
        return path

    def write_review_packet(self, packet: ReviewPacket) -> Path:
        request = self.get_revision(packet.revision_id)
        if request.status != RevisionStatus.REVIEW_REQUIRED:
            raise InvalidTransitionError("Review packets require revision status REVIEW_REQUIRED.")
        path = self._revision_dir(packet.revision_id) / "review_packet.json"
        self._write_json(path, packet)
        return path

    def candidate_dir(self, candidate_id: str) -> Path:
        _validate_identifier("candidate_id", candidate_id)
        return self.registry_root / "candidates" / candidate_id

    def revision_dir(self, revision_id: str) -> Path:
        return self._revision_dir(revision_id)

    def get_published_context(self, context_id: str) -> dict[str, Any] | None:
        path = self._published_context_path(context_id)
        return self._read_json(path) if path.exists() else None

    def publish_candidate(self, candidate_id: str) -> dict[str, Any]:
        candidate = self.get_candidate(candidate_id)
        if candidate.status == CandidateStatus.APPROVED:
            candidate = self.transition_candidate(
                candidate_id,
                CandidateStatus.PUBLISHED,
                expected_status=CandidateStatus.APPROVED,
            )
        elif candidate.status != CandidateStatus.PUBLISHED:
            raise InvalidTransitionError(
                f"Candidate {candidate_id} must be APPROVED before publish."
            )
        current = self.get_published_context(candidate.context_id)
        if current and current.get("candidate_id") == candidate_id:
            return current
        publication = self._publication_record(
            candidate=candidate,
            previous_candidate_id=current.get("candidate_id") if current else None,
            action="publish",
        )
        self._write_json(
            self._publication_history_path(candidate.context_id, publication["publication_id"]),
            publication,
        )
        self._write_json(self._published_context_path(candidate.context_id), publication)
        return publication

    def rollback_context(
        self,
        context_id: str,
        *,
        target_candidate_id: str | None = None,
    ) -> dict[str, Any]:
        current = self.get_published_context(context_id)
        if not current:
            raise RecordNotFoundError(f"No published candidate for context {context_id}.")
        resolved_target_id = target_candidate_id or current.get("previous_candidate_id")
        if not resolved_target_id:
            raise InvalidTransitionError(f"Context {context_id} has no previous candidate to restore.")
        target = self.get_candidate(str(resolved_target_id))
        if target.context_id != context_id:
            raise InvalidTransitionError(
                f"Candidate {target.candidate_id} belongs to context {target.context_id}, not {context_id}."
            )
        if target.status != CandidateStatus.PUBLISHED:
            raise InvalidTransitionError(
                f"Rollback target {target.candidate_id} must already be PUBLISHED."
            )
        publication = self._publication_record(
            candidate=target,
            previous_candidate_id=str(current["candidate_id"]),
            action="rollback",
        )
        self._write_json(
            self._publication_history_path(context_id, publication["publication_id"]),
            publication,
        )
        self._write_json(self._published_context_path(context_id), publication)
        return publication

    def _all_questions_answered(self, task: HumanTask) -> bool:
        answered = {
            data.get("question_id")
            for path in self._answers_dir(task.revision_id).glob("*.json")
            for data in [self._read_json(path)]
            if data.get("task_id") == task.task_id
        }
        return all(not question.required or question.question_id in answered for question in task.questions)

    def _has_answer(self, task: HumanTask, question_id: str) -> bool:
        return any(
            data.get("task_id") == task.task_id and data.get("question_id") == question_id
            for path in self._answers_dir(task.revision_id).glob("*.json")
            for data in [self._read_json(path)]
        )

    def _has_open_task(self, revision_id: str, task_type: HumanTaskType) -> bool:
        tasks_dir = self._revision_dir(revision_id) / "human_tasks"
        return any(
            task.task_type == task_type and task.status == HumanTaskStatus.OPEN
            for path in tasks_dir.glob("*.json")
            for task in [_human_task_from_dict(self._read_json(path))]
        )

    def _has_answered_task(self, revision_id: str, task_type: HumanTaskType) -> bool:
        tasks_dir = self._revision_dir(revision_id) / "human_tasks"
        return any(
            task.task_type == task_type and task.status == HumanTaskStatus.ANSWERED
            for path in tasks_dir.glob("*.json")
            for task in [_human_task_from_dict(self._read_json(path))]
        )

    def _candidate_path(self, candidate_id: str) -> Path:
        return self.candidate_dir(candidate_id) / "candidate.json"

    def _revision_dir(self, revision_id: str) -> Path:
        _validate_identifier("revision_id", revision_id)
        return self.registry_root / "revisions" / revision_id

    def _change_request_path(self, revision_id: str) -> Path:
        return self._revision_dir(revision_id) / "change_request.json"

    def _human_task_path(self, revision_id: str, task_id: str) -> Path:
        _validate_identifier("task_id", task_id)
        return self._revision_dir(revision_id) / "human_tasks" / f"{task_id}.json"

    def _answers_dir(self, revision_id: str) -> Path:
        return self._revision_dir(revision_id) / "answers"

    def _answer_path(self, revision_id: str, answer_id: str) -> Path:
        _validate_identifier("answer_id", answer_id)
        return self._answers_dir(revision_id) / f"{answer_id}.json"

    def _published_context_path(self, context_id: str) -> Path:
        _validate_identifier("context_id", context_id)
        return self.registry_root / "contexts" / context_id / "published.json"

    def _publication_history_path(self, context_id: str, publication_id: str) -> Path:
        _validate_identifier("publication_id", publication_id)
        return self.registry_root / "contexts" / context_id / "publish_history" / f"{publication_id}.json"

    def _publication_record(
        self,
        *,
        candidate: CandidateRecord,
        previous_candidate_id: str | None,
        action: str,
    ) -> dict[str, Any]:
        return {
            "publication_id": _new_id("publication"),
            "action": action,
            "context_id": candidate.context_id,
            "candidate_id": candidate.candidate_id,
            "version": candidate.version,
            "project_path": candidate.project_path,
            "previous_candidate_id": previous_candidate_id,
            "published_at": _utc_now(),
        }

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise RecordNotFoundError(f"Registry record not found: {path}")
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise RevisionStoreError(f"Registry record must be a JSON object: {path}")
        return loaded

    def _write_json(self, path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(_json_value(value), ensure_ascii=False, indent=2) + "\n"
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as temporary_file:
                temporary_file.write(payload)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_name, path)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise


def _candidate_from_dict(data: dict[str, Any]) -> CandidateRecord:
    provenance = [_provenance_from_dict(item) for item in data.get("provenance", [])]
    release_eligible = data.get("release_eligible")
    if release_eligible is None:
        release_eligible = not any(
            "DEVELOPMENT_ONLY" in item.statement for item in provenance
        )
    return CandidateRecord(
        candidate_id=str(data["candidate_id"]),
        context_id=str(data["context_id"]),
        version=int(data["version"]),
        project_path=str(data["project_path"]),
        status=CandidateStatus(data["status"]),
        base_candidate_id=data.get("base_candidate_id"),
        revision_id=data.get("revision_id"),
        provenance=provenance,
        release_eligible=bool(release_eligible),
        created_at=str(data["created_at"]),
        updated_at=str(data["updated_at"]),
    )


def _change_request_from_dict(data: dict[str, Any]) -> ChangeRequest:
    return ChangeRequest(
        revision_id=str(data["revision_id"]),
        base_candidate_id=str(data["base_candidate_id"]),
        base_candidate_version=int(data["base_candidate_version"]),
        candidate_id=str(data["candidate_id"]),
        user_instruction=str(data["user_instruction"]),
        requested_scope=[str(item) for item in data.get("requested_scope", [])],
        provenance=_provenance_from_dict(data["provenance"]),
        risk_level=RiskLevel(data["risk_level"]),
        status=RevisionStatus(data["status"]),
        created_at=str(data["created_at"]),
        updated_at=str(data["updated_at"]),
    )


def _human_task_from_dict(data: dict[str, Any]) -> HumanTask:
    return HumanTask(
        task_id=str(data["task_id"]),
        revision_id=str(data["revision_id"]),
        task_type=HumanTaskType(data["task_type"]),
        status=HumanTaskStatus(data["status"]),
        questions=[HumanQuestion(**item) for item in data.get("questions", [])],
        created_at=str(data["created_at"]),
        resolved_at=data.get("resolved_at"),
    )


def _human_answer_from_dict(data: dict[str, Any]) -> HumanAnswer:
    return HumanAnswer(
        answer_id=str(data["answer_id"]),
        revision_id=str(data["revision_id"]),
        task_id=str(data["task_id"]),
        question_id=str(data["question_id"]),
        answer=str(data["answer"]),
        provenance=_provenance_from_dict(data["provenance"]),
        created_at=str(data["created_at"]),
    )


def _provenance_from_dict(data: dict[str, Any]) -> Provenance:
    return Provenance(
        provenance_type=ProvenanceType(data["provenance_type"]),
        source_id=str(data["source_id"]),
        statement=str(data["statement"]),
        recorded_at=str(data["recorded_at"]),
    )


def _require_transition(
    kind: str,
    current: Enum,
    target: Enum,
    transitions: dict[Any, set[Any]],
) -> None:
    if target not in transitions[current]:
        raise InvalidTransitionError(
            f"Invalid {kind} transition: {current.value} -> {target.value}."
        )


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _validate_identifier(label: str, value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
        raise ValueError(f"Invalid {label}: {value!r}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
