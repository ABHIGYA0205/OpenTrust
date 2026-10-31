"""End-to-end: generate the simulated network, then assert the two headline numbers.

    1. The coordinated campaign is caught (all campaign PRs flagged).
    2. No legitimate newcomer is quarantined.

This is the same harness that reports the numbers in the pitch.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def network(tmp_path_factory):
    out = tmp_path_factory.mktemp("network")
    subprocess.run(
        [sys.executable, str(ROOT / "tools" / "gen_network.py"), "--out", str(out)],
        check=True,
        capture_output=True,
    )
    return out


def _load_prs(incoming: Path) -> list[dict]:
    prs: list[dict] = []
    for path in sorted(incoming.glob("*.json")):
        data = json.loads(path.read_text())
        prs.extend(data if isinstance(data, list) else [data])
    return prs


def test_network_loads_and_verifies(network):
    from opentrust.store import load_network

    loaded = load_network(network / "manifest.json")
    assert len(loaded.projects) == 40
    assert sum(p.report.rejected for p in loaded) == 0
    assert len(loaded.of_type("vouch")) > 20


def test_campaign_is_detected_with_evidence(network):
    from opentrust.campaign import detect_campaigns
    from opentrust.signals import PR

    prs = [PR.from_dict(d) for d in _load_prs(network / "incoming")]
    campaigns = detect_campaigns(prs)

    assert len(campaigns) == 1, f"expected exactly one campaign, got {len(campaigns)}"
    campaign = campaigns[0]
    assert campaign.score >= 0.6
    assert len(campaign.authors) >= 30
    assert len(campaign.affected_projects) >= 20
    assert campaign.evidence["mean_pairwise_similarity"] >= 0.8
    assert campaign.evidence["example_pairs"], "an alert must carry example pairs"
    assert campaign.evidence["signals_fired"] >= 3
    assert "accounts" in campaign.explanation


def test_campaign_prs_are_flagged_and_legit_prs_are_not(network):
    from opentrust.campaign import detect_campaigns
    from opentrust.signals import PR

    prs = [PR.from_dict(d) for d in _load_prs(network / "incoming")]
    labels = json.loads((network / "labels.json").read_text())
    campaigns = detect_campaigns(prs)
    flagged = {pr.pr_id for c in campaigns for pr in c.prs}

    campaign_prs = set(labels["campaign"])
    legit_prs = set(labels["legit"])
    recall = len(flagged & campaign_prs) / len(campaign_prs)
    false_positives = len(flagged & legit_prs)

    assert recall >= 0.9, f"campaign recall too low: {recall:.2f}"
    assert false_positives == 0, f"{false_positives} legitimate PRs were flagged"


def test_legit_newcomers_are_not_quarantined(network):
    """The fairness half of the rubric: unknown is never a rejection."""
    from opentrust.eigentrust import personal_trust
    from opentrust.graph import from_network
    from opentrust.policy import policy_from_records
    from opentrust.reputation import score_subject
    from opentrust.store import load_network

    loaded = load_network(network / "manifest.json")
    weights = personal_trust(from_network(loaded), seed="proj-a")
    policy = policy_from_records(loaded.records(), "proj-a")

    newcomers = {pr["author"] for pr in _load_prs(network / "incoming") if pr["author"].startswith("github:@newcomer")}
    verdicts = {
        handle: score_subject(
            loaded.records(), weights, policy, handle, viewer="proj-a"
        ).verdict
        for handle in newcomers
    }
    quarantined = [h for h, v in verdicts.items() if v == "quarantined"]
    assert not quarantined, f"legitimate newcomers quarantined: {quarantined}"


def test_slide_case_vouch_in_denounce_ignored(network):
    """@new-dev: trusted via proj-b's vouch; proj-x's denounce has no effect."""
    from opentrust.eigentrust import personal_trust
    from opentrust.graph import from_network
    from opentrust.policy import policy_from_records
    from opentrust.reputation import score_subject
    from opentrust.store import load_network

    loaded = load_network(network / "manifest.json")
    weights = personal_trust(from_network(loaded), seed="proj-a")
    policy = policy_from_records(loaded.records(), "proj-a")
    result = score_subject(
        loaded.records(), weights, policy, "github:@new-dev", viewer="proj-a"
    )

    assert result.verdict == "trusted"
    assert "proj-x" in [i.issuer for i in result.ignored]
    assert weights["proj-x"] < policy.min_denounce_trust


def test_bad_actor_with_corroborated_denouncements_is_quarantined(network):
    from opentrust.eigentrust import personal_trust
    from opentrust.graph import from_network
    from opentrust.policy import policy_from_records
    from opentrust.reputation import score_subject
    from opentrust.store import load_network

    loaded = load_network(network / "manifest.json")
    weights = personal_trust(from_network(loaded), seed="proj-a")
    policy = policy_from_records(loaded.records(), "proj-a")
    result = score_subject(
        loaded.records(), weights, policy, "github:@slop-account", viewer="proj-a"
    )
    assert result.verdict == "quarantined"
