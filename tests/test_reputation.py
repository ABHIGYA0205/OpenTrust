"""Reputation scoring, including the exact case from the problem statement:

    "Let in: vouched by Project B, which you trust.
     X's denounce is ignored: you don't trust X."
"""

from __future__ import annotations

from datetime import datetime, timezone

from opentrust import crypto, records
from opentrust.policy import Policy
from opentrust.reputation import score_subject

NOW = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)


def sign(record: dict) -> dict:
    private, _ = crypto.new_keypair()
    return crypto.sign_record(record, private)


def test_vouch_from_trusted_project_makes_contributor_trusted():
    vouches = [
        sign(
            records.build_vouch(
                issuer="proj-b",
                subject="github:@new-dev",
                scope=["code_quality"],
                reason="Fixed a real null-dereference and added the test.",
            )
        )
    ]
    weights = {"proj-b": 0.71}
    result = score_subject(vouches, weights, Policy(), "github:@new-dev", "proj-a", NOW)
    assert result.verdict == "trusted"
    assert result.score > 0


def test_denounce_from_untrusted_project_is_ignored():
    records_ = [
        sign(
            records.build_vouch(
                issuer="proj-b",
                subject="github:@new-dev",
                scope=["code_quality"],
                reason="Good work.",
            )
        ),
        sign(
            records.build_denounce(
                issuer="proj-x",
                subject="github:@new-dev",
                reason="Low quality contribution.",
                evidence=["https://example.com/pr/9"],
                severity="high",
            )
        ),
    ]
    weights = {"proj-b": 0.71, "proj-x": 0.0}
    result = score_subject(records_, weights, Policy(), "github:@new-dev", "proj-a", NOW)

    assert result.verdict == "trusted"
    assert [i.issuer for i in result.ignored] == ["proj-x"]
    assert result.negatives == []
    assert "below the" in result.ignored[0].why


def test_same_network_different_viewpoints_disagree():
    """Decentralisation made visible: X sees what A does not."""
    records_ = [
        sign(
            records.build_denounce(
                issuer="proj-x",
                subject="github:@new-dev",
                reason="Low quality contribution.",
                evidence=["https://example.com/pr/9"],
                severity="high",
            )
        )
    ]
    trust_of_a = {"proj-x": 0.0}
    trust_of_x = {"proj-x": 1.0}
    from_a = score_subject(records_, trust_of_a, Policy(), "github:@new-dev", "proj-a", NOW)
    from_x = score_subject(records_, trust_of_x, Policy(), "github:@new-dev", "proj-x", NOW)
    assert from_a.verdict == "unknown"
    assert from_x.verdict == "quarantined"


def test_corroborated_denouncements_quarantine_a_bad_actor():
    denounces = [
        sign(
            records.build_denounce(
                issuer=issuer,
                subject="github:@slop",
                reason="Identical docs-only PR to 40 projects.",
                evidence=["https://example.com/pr/500"],
                severity="high",
            )
        )
        for issuer in ("proj-a", "proj-b", "proj-c")
    ]
    weights = {"proj-a": 1.0, "proj-b": 0.8, "proj-c": 0.7}
    result = score_subject(denounces, weights, Policy(), "github:@slop", "proj-a", NOW)
    assert result.verdict == "quarantined"
    assert len(result.negatives) == 3


def test_no_history_is_unknown_not_quarantined():
    result = score_subject([], {}, Policy(), "github:@brand-new", "proj-a", NOW)
    assert result.verdict == "unknown"
    assert result.has_history is False
    assert "not a rejection" in result.explain()


def test_retraction_removes_the_original_contribution():
    original = sign(
        records.build_denounce(
            issuer="proj-b",
            subject="github:@person",
            reason="Spam.",
            evidence=["https://example.com/pr/1"],
            severity="high",
        )
    )
    retraction = sign(
        records.build_retract(
            issuer="proj-b",
            target=crypto.record_digest(original),
            reason="After review this PR was legitimate; withdrawing.",
        )
    )
    weights = {"proj-b": 0.9}
    before = score_subject([original], weights, Policy(), "github:@person", "proj-a", NOW)
    after = score_subject(
        [original, retraction], weights, Policy(), "github:@person", "proj-a", NOW
    )
    assert before.verdict == "quarantined"
    assert after.verdict == "unknown"
    assert after.negatives == []


def test_expired_vouch_is_not_counted():
    old = sign(
        records.build_vouch(
            issuer="proj-b",
            subject="github:@alice",
            scope=["code_quality"],
            reason="Good work.",
            issued_at="2024-01-01T00:00:00Z",
            expires_at="2025-01-01T00:00:00Z",
        )
    )
    result = score_subject([old], {"proj-b": 0.9}, Policy(), "github:@alice", "proj-a", NOW)
    assert result.verdict == "unknown"
