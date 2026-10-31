"""Evaluation harness: the two headline numbers for the pitch.

    python tools/evaluate.py --network network

Reports:

1. Campaign recall — of the coordinated campaign, how much did we catch?
2. False positives — did we flag legitimate contributions?
3. Fairness — how many legitimate newcomers were quarantined?
4. Separation — reputation scores of a bad actor vs honest newcomers.
5. Tier-1 vs Tier-2 — how many paraphrased payloads each tier catches.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opentrust.campaign import detect_campaigns  # noqa: E402
from opentrust.eigentrust import personal_trust  # noqa: E402
from opentrust.graph import from_network  # noqa: E402
from opentrust.policy import Policy, policy_from_records  # noqa: E402
from opentrust.reputation import score_subject  # noqa: E402
from opentrust.signals import PR  # noqa: E402
from opentrust.similarity import embedding_similarity  # noqa: E402
from opentrust.store import load_network  # noqa: E402


def load_prs(directory: Path) -> list[dict]:
    prs: list[dict] = []
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text())
        prs.extend(data if isinstance(data, list) else [data])
    return prs


def pct(part: int, whole: int) -> str:
    return f"{(100.0 * part / whole) if whole else 0.0:5.1f}%"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--network", default="network")
    parser.add_argument("--viewer", default="proj-a")
    parser.add_argument("--tier2", action="store_true")
    args = parser.parse_args()

    root = Path(args.network)
    raw_prs = load_prs(root / "incoming")
    prs = [PR.from_dict(item) for item in raw_prs]
    labels = json.loads((root / "labels.json").read_text())
    policy = Policy()

    start = time.perf_counter()
    campaigns = detect_campaigns(prs, policy, tier2=args.tier2)
    elapsed = time.perf_counter() - start
    flagged = {pr.pr_id for campaign in campaigns for pr in campaign.prs}

    identical = set(labels["campaign"])
    paraphrased = set(labels.get("campaign_paraphrased", []))
    legit = set(labels["legit"])

    caught_identical = len(flagged & identical)
    caught_paraphrased = len(flagged & paraphrased)
    false_positives = len(flagged & legit)

    network = load_network(root / "manifest.json")
    project_policy = policy_from_records(network.records(), args.viewer)
    weights = personal_trust(from_network(network), seed=args.viewer,
                             max_hops=project_policy.max_trust_hops)

    newcomers = sorted({pr.author for pr in prs if pr.author.startswith("github:@newcomer")})
    verdicts = {
        handle: score_subject(
            network.records(), weights, project_policy, handle, viewer=args.viewer
        )
        for handle in newcomers
    }
    quarantined = [h for h, v in verdicts.items() if v.verdict == "quarantined"]
    trusted = [h for h, v in verdicts.items() if v.verdict == "trusted"]

    bad_actor = score_subject(
        network.records(), weights, project_policy, "github:@slop-account", viewer=args.viewer
    )
    new_dev = score_subject(
        network.records(), weights, project_policy, "github:@new-dev", viewer=args.viewer
    )

    tier2_available = embedding_similarity(["probe a", "probe b"]) is not None

    print("=" * 68)
    print(f"EVALUATION   network={root}   viewer={args.viewer}")
    print("=" * 68)
    print(f"projects in network           : {len(network.projects)}")
    print(f"records (signature-verified)  : {sum(p.report.accepted for p in network)}")
    print(f"incoming PRs analysed         : {len(prs)}")
    print()
    print("-- campaign detection -------------------------------------------------")
    print(f"identical-payload PRs         : {len(identical):3d}   caught {caught_identical:3d}   recall {pct(caught_identical, len(identical))}")
    print(f"paraphrased-payload PRs       : {len(paraphrased):3d}   caught {caught_paraphrased:3d}   recall {pct(caught_paraphrased, len(paraphrased))}")
    print(f"legitimate PRs                : {len(legit):3d}   flagged {false_positives:3d}   false positives {pct(false_positives, len(legit))}")
    print(f"campaigns reported            : {len(campaigns)}")
    for campaign in campaigns:
        print(f"    {campaign.summary()}")
    print()
    print("-- fairness -----------------------------------------------------------")
    print(f"legitimate newcomers          : {len(newcomers):3d}   quarantined {len(quarantined):3d}")
    print(f"                             :      unknown {len(newcomers) - len(trusted) - len(quarantined):3d}   trusted {len(trusted):3d}")
    if quarantined:
        print(f"    ! quarantined: {quarantined}")
    print()
    print("-- reputation separation ---------------------------------------------")
    print(f"denounced bad actor           : {bad_actor.verdict:12s} {bad_actor.score:+7.3f}")
    print(f"vouched newcomer (@new-dev)   : {new_dev.verdict:12s} {new_dev.score:+7.3f}")
    legit_scores = [verdicts[h].score for h in newcomers]
    print(f"unvouched newcomers (median)  : {'unknown':12s} {statistics.median(legit_scores):+7.3f}")
    print(f"denouncements ignored (untrusted issuers): {len(new_dev.ignored)} on @new-dev")
    print()
    print("-- model tiers --------------------------------------------------------")
    print(f"tier 1 (minhash, always on)   : available")
    print(f"tier 2 (local embeddings)     : {'available' if tier2_available else 'unavailable (no Ollama) -- Tier 1 only'}")
    print(f"runtime                       : {elapsed:.2f}s for {len(prs)} PRs")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
