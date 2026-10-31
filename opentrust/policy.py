"""Per-project policy: published thresholds, so every judgement is auditable.

A project publishes its policy as a signed ``policy`` record. Anyone can then replay
the decision and check it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

__all__ = ["Policy", "DEFAULT_SCOPE_WEIGHTS", "policy_from_records"]

DEFAULT_SCOPE_WEIGHTS: dict[str, float] = {
    "code_quality": 1.0,
    "security_review": 1.25,
    "responsiveness": 0.8,
    "community": 0.9,
    "docs": 0.5,
}


@dataclass
class Policy:
    # A denouncement from a project you trust less than this is recorded but has
    # no effect. This is what makes "X's denounce is ignored" structural rather
    # than a special case.
    min_denounce_trust: float = 0.10
    # Verdict boundaries on the reputation score. A vouch from one well-connected
    # trusted peer is worth roughly 0.2 after EigenTrust normalisation, so 0.15 is
    # "one trusted peer vouching is enough" rather than an arbitrary cut.
    trusted_at: float = 0.10
    quarantine_at: float = -0.30
    # Trust propagation depth. HACKATHON.md: "By default we follow one hop: if A
    # trusts B, A sees B's vouches, but A doesn't automatically trust everyone B
    # trusts. A project can allow more hops in its policy, and each extra hop counts
    # for less." 1 = one hop; None = unlimited (decay only).
    max_trust_hops: int | None = 1
    # Vouch expiry / recency decay.
    half_life_days: float = 180.0
    # Campaign detection.
    similarity_threshold: float = 0.85
    # Cosine threshold for Tier-2 embeddings. Embedding scores sit on a different
    # scale from shingle overlap: on the fixture network reworded spam scores
    # >= 0.85 against the campaign and unrelated real PRs <= 0.36, so 0.80 keeps a
    # wide margin on both sides.
    semantic_threshold: float = 0.80
    min_cohort_size: int = 5
    campaign_window_minutes: int = 120
    min_campaign_signals: int = 3
    # A newcomer is never quarantined for lack of history.
    unknown_is_rejection: bool = False
    scope_weights: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_SCOPE_WEIGHTS)
    )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Policy":
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)


def policy_from_records(records: list[dict], project_id: str) -> Policy:
    """Latest published policy record from ``project_id``, else the defaults."""
    mine = [
        r
        for r in records
        if r.get("type") == "policy" and r.get("issuer") == project_id
    ]
    if not mine:
        return Policy()
    latest = max(mine, key=lambda r: r.get("issued_at", ""))
    return Policy.from_dict(latest.get("policy", {}))
