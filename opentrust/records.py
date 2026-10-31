"""Record types, builders and validation.

Six record types make up the whole protocol:

``vouch``          scoped positive claim about a subject, with evidence and expiry
``denounce``       negative claim; requires evidence and a severity
``retract``        append-only withdrawal of a previous record, by content digest
``trust_edge``     "I trust project X's judgement", directed and weighted
``campaign_alert`` network-level coordinated-campaign finding, with evidence
``policy``         a project's published thresholds, so its judgements are auditable
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

__all__ = [
    "RecordError",
    "RECORD_TYPES",
    "build_campaign_alert",
    "build_denounce",
    "build_policy",
    "build_retract",
    "build_trust_edge",
    "build_vouch",
    "utcnow",
    "validate",
]

RECORD_TYPES = (
    "vouch",
    "denounce",
    "retract",
    "trust_edge",
    "campaign_alert",
    "policy",
)

REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "vouch": ("issuer", "subject", "scope", "reason", "issued_at"),
    "denounce": ("issuer", "subject", "reason", "evidence", "severity", "issued_at"),
    "retract": ("issuer", "target", "reason", "issued_at"),
    "trust_edge": ("issuer", "target_project", "weight", "issued_at"),
    "campaign_alert": (
        "issuer",
        "window",
        "cohort",
        "evidence",
        "severity",
        "issued_at",
    ),
    "policy": ("issuer", "policy", "issued_at"),
}

SEVERITIES = ("low", "medium", "high")
SCOPES = ("code_quality", "security_review", "responsiveness", "docs", "community")


class RecordError(ValueError):
    """Raised when a record is malformed or unsigned."""


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _expiry(days: int) -> str:
    when = datetime.now(timezone.utc) + timedelta(days=days)
    return when.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate(record: dict[str, Any]) -> dict[str, Any]:
    """Validate shape and semantics. Raises :class:`RecordError`."""
    if not isinstance(record, dict):
        raise RecordError("record must be a JSON object")
    kind = record.get("type")
    if kind not in RECORD_TYPES:
        raise RecordError(f"unknown record type: {kind!r}")
    for field in REQUIRED_FIELDS[kind]:
        if field not in record:
            raise RecordError(f"{kind} record missing field {field!r}")
    if "sig" not in record:
        raise RecordError(f"{kind} record is not signed")
    if not record.get("issuer"):
        raise RecordError("issuer must be a non-empty string")

    if kind == "vouch":
        if not record["scope"]:
            raise RecordError("vouch requires at least one scope")
        bad = [s for s in record["scope"] if s not in SCOPES]
        if bad:
            raise RecordError(f"unknown scope(s): {bad}")
    elif kind == "denounce":
        if record["severity"] not in SEVERITIES:
            raise RecordError(f"severity must be one of {SEVERITIES}")
        if not record["evidence"]:
            raise RecordError("denounce requires at least one evidence URL")
        if not record["reason"].strip():
            raise RecordError("denounce requires a stated reason")
    elif kind == "retract":
        if not str(record["target"]).startswith("sha256:"):
            raise RecordError("retract.target must be a record digest (sha256:...)")
    elif kind == "trust_edge":
        weight = record["weight"]
        if not isinstance(weight, (int, float)) or not 0 < float(weight) <= 1:
            raise RecordError("trust_edge.weight must be in (0, 1]")
    return record


def build_vouch(
    issuer: str,
    subject: str,
    scope: list[str],
    reason: str,
    evidence: list[str] | None = None,
    issued_at: str | None = None,
    expires_at: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "vouch",
        "issuer": issuer,
        "subject": subject,
        "scope": scope,
        "reason": reason,
        "evidence": evidence or [],
        "issued_at": issued_at or utcnow(),
        "expires_at": expires_at or _expiry(365),
    }


def build_denounce(
    issuer: str,
    subject: str,
    reason: str,
    evidence: list[str],
    severity: str = "medium",
    issued_at: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "denounce",
        "issuer": issuer,
        "subject": subject,
        "reason": reason,
        "evidence": evidence,
        "severity": severity,
        "issued_at": issued_at or utcnow(),
    }


def build_trust_edge(
    issuer: str,
    target_project: str,
    weight: float = 0.8,
    issued_at: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "trust_edge",
        "issuer": issuer,
        "target_project": target_project,
        "weight": round(float(weight), 4),
        "issued_at": issued_at or utcnow(),
    }


def build_retract(
    issuer: str, target: str, reason: str, issued_at: str | None = None
) -> dict[str, Any]:
    return {
        "type": "retract",
        "issuer": issuer,
        "target": target,
        "reason": reason,
        "issued_at": issued_at or utcnow(),
    }


def build_policy(
    issuer: str, policy: dict[str, Any], issued_at: str | None = None
) -> dict[str, Any]:
    return {
        "type": "policy",
        "issuer": issuer,
        "policy": policy,
        "issued_at": issued_at or utcnow(),
    }


def build_campaign_alert(
    issuer: str,
    window: dict[str, Any],
    cohort: dict[str, Any],
    evidence: dict[str, Any],
    severity: str = "high",
    affected_projects: list[str] | None = None,
    explanation: str = "",
    issued_at: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "campaign_alert",
        "issuer": issuer,
        "window": window,
        "cohort": cohort,
        "evidence": evidence,
        "severity": severity,
        "affected_projects": affected_projects or [],
        "explanation": explanation,
        "issued_at": issued_at or utcnow(),
    }
