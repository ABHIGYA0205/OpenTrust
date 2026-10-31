"""Reputation scoring from a specific project's point of view.

    score(subject) = sum over live vouches   of trust[issuer] * scope_weight * recency
                   - sum over live denounces of trust[issuer] * severity * corroboration
                     (only when trust[issuer] >= policy.min_denounce_trust)

Every term is recorded on the result object, so any verdict can be explained line by
line. Nothing here consults a language model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import crypto
from .policy import Policy
from .records import SCOPES

__all__ = ["Contribution", "IgnoredRecord", "SubjectScore", "score_subject"]

SEVERITY_WEIGHT = {"low": 0.5, "medium": 1.0, "high": 1.5}


@dataclass
class Contribution:
    kind: str  # "vouch" | "denounce"
    issuer: str
    issuer_trust: float
    value: float
    detail: str


@dataclass
class IgnoredRecord:
    """A statement that was seen but carried no weight from this viewpoint."""

    kind: str  # "vouch" | "denounce"
    issuer: str
    issuer_trust: float
    reason: str
    why: str


@dataclass
class SubjectScore:
    subject: str
    viewer: str
    score: float
    verdict: str
    contributions: list[Contribution] = field(default_factory=list)
    ignored: list[IgnoredRecord] = field(default_factory=list)
    has_history: bool = False

    @property
    def positives(self) -> list[Contribution]:
        return [c for c in self.contributions if c.value > 0]

    @property
    def negatives(self) -> list[Contribution]:
        return [c for c in self.contributions if c.value < 0]

    def explain(self) -> str:
        lines = [
            f"Subject  : {self.subject}",
            f"Viewpoint: {self.viewer}",
            f"Verdict  : {self.verdict.upper()}   (score {self.score:+.3f})",
        ]
        if not self.has_history:
            lines.append("History  : no records — status is UNKNOWN, which is not a rejection.")
        if self.positives:
            lines.append("Counted vouches:")
            for c in self.positives:
                lines.append(f"  + {c.value:.3f}  {c.detail}")
        if self.negatives:
            lines.append("Counted denouncements:")
            for c in self.negatives:
                lines.append(f"  - {abs(c.value):.3f}  {c.detail}")
        if self.ignored:
            lines.append("Ignored statements (issuer carries no weight from this viewpoint):")
            for i in self.ignored:
                lines.append(
                    f"  · [{i.kind}] {i.issuer} (trust {i.issuer_trust:.3f}) — {i.why}"
                )
        return "\n".join(lines)


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _recency(issued_at: str, now: datetime, half_life_days: float) -> float:
    try:
        age_days = max(0.0, (now - _parse(issued_at)).total_seconds() / 86400.0)
    except (ValueError, AttributeError):
        return 1.0
    return 0.5 ** (age_days / half_life_days) if half_life_days > 0 else 1.0


def _scope_weight(scopes: list[str], policy: Policy) -> float:
    weights = [policy.scope_weights.get(s, 1.0) for s in scopes if s in SCOPES]
    return sum(weights) / len(weights) if weights else 0.5


def score_subject(
    records: list[dict],
    trust_weights: dict[str, float],
    policy: Policy,
    subject: str,
    viewer: str,
    now: datetime | None = None,
) -> SubjectScore:
    """Score ``subject`` as seen by ``viewer``.

    ``trust_weights`` comes from :func:`opentrust.eigentrust.personal_trust`, so a
    project you barely trust contributes almost nothing — including a denouncement.
    """
    now = now or datetime.now(timezone.utc)

    # Append-only corrections: a retract disables the record it names.
    retracted = {
        r["target"] for r in records if r.get("type") == "retract" and r.get("target")
    }

    vouches: list[dict] = []
    denounces: list[dict] = []
    for record in records:
        if crypto.record_digest(record) in retracted:
            continue
        if record.get("type") not in ("vouch", "denounce"):
            continue
        if record.get("subject") != subject:
            continue
        expires = record.get("expires_at")
        if expires and record.get("type") == "vouch":
            try:
                if _parse(expires) < now:
                    continue
            except ValueError:
                pass
        (vouches if record["type"] == "vouch" else denounces).append(record)

    result = SubjectScore(
        subject=subject,
        viewer=viewer,
        score=0.0,
        verdict="unknown",
        has_history=bool(vouches or denounces),
    )

    for record in vouches:
        issuer = record["issuer"]
        issuer_trust = 1.0 if issuer == viewer else float(trust_weights.get(issuer, 0.0))
        if issuer_trust <= 0:
            result.ignored.append(
                IgnoredRecord(
                    kind="vouch",
                    issuer=issuer,
                    issuer_trust=issuer_trust,
                    reason=record.get("reason", ""),
                    why="issuer is outside the viewer's trust graph",
                )
            )
            continue
        value = (
            issuer_trust
            * _scope_weight(record.get("scope", []), policy)
            * _recency(record.get("issued_at", ""), now, policy.half_life_days)
        )
        result.score += value
        result.contributions.append(
            Contribution(
                kind="vouch",
                issuer=issuer,
                issuer_trust=issuer_trust,
                value=value,
                detail=(
                    f"vouch by {issuer} (trust {issuer_trust:.3f}, "
                    f"scope {','.join(record.get('scope', []))}) — "
                    f"{record.get('reason', '')}"
                ),
            )
        )

    # Independent trusted issuers who denounce make a denouncement more credible.
    def weight_of(issuer: str) -> float:
        # Your own records always carry full weight; everyone else is discounted by
        # how much you trust them from this viewpoint.
        return 1.0 if issuer == viewer else float(trust_weights.get(issuer, 0.0))

    qualifying = [r for r in denounces if weight_of(r["issuer"]) >= policy.min_denounce_trust]
    independent_issuers = {r["issuer"] for r in qualifying}
    corroboration = 1.0 + math.log1p(max(0, len(independent_issuers) - 1))

    for record in denounces:
        issuer = record["issuer"]
        issuer_trust = weight_of(issuer)
        if issuer_trust < policy.min_denounce_trust:
            result.ignored.append(
                IgnoredRecord(
                    kind="denounce",
                    issuer=issuer,
                    issuer_trust=issuer_trust,
                    reason=record.get("reason", ""),
                    why=(
                        f"issuer trust {issuer_trust:.3f} is below the "
                        f"min_denounce_trust {policy.min_denounce_trust:.2f}"
                    ),
                )
            )
            continue
        severity = SEVERITY_WEIGHT.get(record.get("severity", "medium"), 1.0)
        value = -(
            issuer_trust
            * severity
            * corroboration
            * _recency(record.get("issued_at", ""), now, policy.half_life_days)
        )
        result.score += value
        result.contributions.append(
            Contribution(
                kind="denounce",
                issuer=issuer,
                issuer_trust=issuer_trust,
                value=value,
                detail=(
                    f"denounce by {issuer} (trust {issuer_trust:.3f}, "
                    f"severity {record.get('severity')}, corroboration x{corroboration:.2f}) — "
                    f"{record.get('reason', '')}"
                ),
            )
        )

    if not result.has_history:
        result.verdict = "unknown"
    elif result.score >= policy.trusted_at:
        result.verdict = "trusted"
    elif result.score <= policy.quarantine_at:
        result.verdict = "quarantined"
    else:
        result.verdict = "unknown"
    return result
