from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import BoundedCodexTask, IsolationReceipt, new_record_id


ISOLATION_HMAC_ENV = "DATA_AGENT_ISOLATION_HMAC_KEY"
ISOLATION_ENVIRONMENT_ID_ENV = "DATA_AGENT_ISOLATION_ENVIRONMENT_ID"
MAX_RECEIPT_TTL = timedelta(minutes=30)
MAX_CLOCK_SKEW = timedelta(minutes=5)
REQUIRED_ISOLATION_PROBES = (
    "process_tree_isolated",
    "child_process_policy_inherited",
    "candidate_write_allowed",
    "evidence_read_allowed",
    "evidence_write_denied",
    "base_snapshot_not_mounted",
    "outside_workspace_read_denied",
    "outside_workspace_write_denied",
    "tool_network_denied",
    "credential_scope_minimized",
)


def create_isolation_receipt(
    *,
    job: BoundedCodexTask,
    environment_id: str,
    issuer: str,
    backend: str,
    hmac_key: str,
    probes: dict[str, bool],
    issued_at: datetime | None = None,
    ttl: timedelta = timedelta(minutes=10),
    receipt_id: str | None = None,
) -> IsolationReceipt:
    issued = issued_at or datetime.now(timezone.utc)
    if issued.tzinfo is None or issued.utcoffset() is None:
        raise ValueError("Isolation receipt issued_at must be timezone-aware.")
    if ttl <= timedelta(0) or ttl > MAX_RECEIPT_TTL:
        raise ValueError("Isolation receipt TTL must be positive and at most 30 minutes.")
    schema_fingerprint = job.data_identity.get("schema_fingerprint")
    if not schema_fingerprint:
        raise ValueError("Isolation receipt requires the Job schema fingerprint.")
    receipt = IsolationReceipt(
        schema_version=1,
        receipt_id=receipt_id or new_record_id("isolation"),
        job_id=job.job_id,
        job_contract_sha256=job_execution_contract_sha256(job),
        eval_target_sha256=job.eval_target_sha256,
        evidence_manifest_sha256=job.evidence_manifest_sha256,
        schema_fingerprint=schema_fingerprint,
        environment_id=environment_id,
        issuer=issuer,
        backend=backend,
        tool_network_policy="DENY",
        provider_network_policy="CONTROL_PLANE_ONLY",
        writable_root=job.writable_root,
        probes=dict(probes),
        issued_at=_utc_text(issued),
        expires_at=_utc_text(issued + ttl),
        signature="hmac-sha256:" + "0" * 64,
    )
    return replace(receipt, signature=_sign(receipt, hmac_key))


def load_isolation_receipt(*, path: Path, project_root: Path) -> IsolationReceipt:
    resolved = path.resolve()
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError as exc:
        raise ValueError("Isolation receipt must remain inside project-root.") from exc
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Isolation receipt is unavailable or invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Isolation receipt must be a JSON object.")
    return IsolationReceipt.from_dict(payload)


def verify_isolation_receipt(
    *,
    job: BoundedCodexTask,
    receipt: IsolationReceipt,
    hmac_key: str,
    environment_id: str,
    now: datetime | None = None,
) -> str | None:
    if len(hmac_key.encode("utf-8")) < 32:
        return "Isolation HMAC key must contain at least 32 bytes."
    if receipt.job_id != job.job_id:
        return "Isolation receipt is bound to a different Job."
    if receipt.job_contract_sha256 != job_execution_contract_sha256(job):
        return "Isolation receipt Job contract hash does not match."
    if receipt.eval_target_sha256 != job.eval_target_sha256:
        return "Isolation receipt EvalTarget hash does not match."
    if receipt.evidence_manifest_sha256 != job.evidence_manifest_sha256:
        return "Isolation receipt evidence manifest hash does not match."
    if receipt.schema_fingerprint != job.data_identity.get("schema_fingerprint"):
        return "Isolation receipt schema fingerprint does not match."
    if receipt.writable_root != job.writable_root:
        return "Isolation receipt writable root does not match."
    if receipt.environment_id != environment_id:
        return "Isolation receipt does not match the active execution environment."
    missing = [name for name in REQUIRED_ISOLATION_PROBES if receipt.probes.get(name) is not True]
    if missing:
        return "Isolation receipt has missing or failed probes: " + ", ".join(missing)
    current = now or datetime.now(timezone.utc)
    issued = _parse_utc(receipt.issued_at)
    expires = _parse_utc(receipt.expires_at)
    if issued > current + MAX_CLOCK_SKEW:
        return "Isolation receipt issued_at is too far in the future."
    if expires <= current:
        return "Isolation receipt has expired."
    if expires <= issued or expires - issued > MAX_RECEIPT_TTL:
        return "Isolation receipt validity window is invalid."
    if not hmac.compare_digest(receipt.signature, _sign(receipt, hmac_key)):
        return "Isolation receipt signature is invalid."
    return None


def job_execution_contract_sha256(job: BoundedCodexTask) -> str:
    payload = job.to_dict()
    payload.pop("status", None)
    return _canonical_sha256(payload)


def _sign(receipt: IsolationReceipt, hmac_key: str) -> str:
    if len(hmac_key.encode("utf-8")) < 32:
        raise ValueError("Isolation HMAC key must contain at least 32 bytes.")
    payload = receipt.to_dict()
    payload.pop("signature", None)
    digest = hmac.new(
        hmac_key.encode("utf-8"),
        _canonical_json(payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"hmac-sha256:{digest}"


def _canonical_sha256(value: Any) -> str:
    digest = hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
