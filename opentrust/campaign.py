"""Network-level coordinated campaign detection.

Individual reputation cannot see a campaign: each maintainer receives one plausible
pull request. The signal only exists across projects, so this module works on the
whole incoming stream at once:

1. Cluster authors whose payloads are near-identical (Tier 1 shingles, optionally
   Tier 2 embeddings) *and* who target different projects.
2. Score each cluster on independent signals: payload similarity, cohort size,
   project overlap, burstiness, account newness, triviality.
3. Emit a signed ``campaign_alert`` with the evidence, if at least
   ``policy.min_campaign_signals`` signals fire and the cohort is large enough.

Deliberately, no single signal can quarantine anyone — account age alone, or a single
similarity pair, is how legitimate newcomers get punished.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import timedelta

from .policy import Policy
from .signals import PR, account_newness, triviality
from .similarity import pairwise_similarity, shingles

__all__ = ["Campaign", "detect_campaigns"]

WEIGHTS = {
    "similarity_density": 0.30,
    "cohort_size": 0.15,
    "project_overlap": 0.15,
    "burstiness": 0.15,
    "account_newness": 0.15,
    "triviality_rate": 0.10,
}


@dataclass
class Campaign:
    authors: list[str]
    prs: list[PR]
    score: float
    signals: dict[str, float]
    evidence: dict
    window: dict
    explanation: str = ""
    affected_projects: list[str] = field(default_factory=list)

    def to_record_fields(self) -> dict:
        return {
            "window": self.window,
            "cohort": {
                "accounts": len(self.authors),
                "median_account_age_days": self.evidence["median_account_age_days"],
                "projects_hit": len(self.affected_projects),
            },
            "evidence": self.evidence,
            "severity": "high" if self.score >= 0.75 else "medium",
            "affected_projects": self.affected_projects,
            "explanation": self.explanation,
        }

    def summary(self) -> str:
        return (
            f"{len(self.authors)} accounts · {len(self.prs)} PRs · "
            f"{len(self.affected_projects)} projects · "
            f"mean similarity {self.evidence['mean_pairwise_similarity']:.2f} · "
            f"score {self.score:.2f}"
        )


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def groups(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for node in list(self.parent):
            out.setdefault(self.find(node), []).append(node)
        return out


def _cluster(prs: list[PR], policy: Policy, tier2: bool = False) -> list[list[str]]:
    """Group authors whose PRs are near-identical but target different projects."""
    if len(prs) < 2:
        return []
    matrix = pairwise_similarity([pr.text for pr in prs])
    if tier2:
        from .similarity import embedding_similarity

        semantic = embedding_similarity([pr.text for pr in prs])
        if semantic is not None:
            matrix = [
                [max(a, b) for a, b in zip(row_a, row_b)]
                for row_a, row_b in zip(matrix, semantic)
            ]

    uf = _UnionFind()
    for i, left in enumerate(prs):
        uf.find(left.author)
        for j in range(i + 1, len(prs)):
            right = prs[j]
            if left.author == right.author:
                continue
            if left.project == right.project:
                continue
            if matrix[i][j] >= policy.similarity_threshold:
                uf.union(left.author, right.author)
    return [sorted(group) for group in uf.groups().values() if len(group) >= policy.min_cohort_size]


def _measure(prs: list[PR]) -> dict[str, float]:
    """Mean of Tier-1 similarity over cross-project pairs of *different* authors."""
    values = []
    for i, left in enumerate(prs):
        for right in prs[i + 1 :]:
            if left.author == right.author:
                continue
            values.append(
                len(shingles(left.text) & shingles(right.text))
                / max(1, len(shingles(left.text) | shingles(right.text)))
            )
    return {"mean": round(statistics.fmean(values), 3) if values else 0.0}


def detect_campaigns(
    prs: list[PR],
    policy: Policy | None = None,
    tier2: bool = False,
) -> list[Campaign]:
    policy = policy or Policy()
    campaigns: list[Campaign] = []

    for authors in _cluster(prs, policy, tier2=tier2):
        author_set = set(authors)
        cohort_prs = [pr for pr in prs if pr.author in author_set]
        if len(cohort_prs) < policy.min_cohort_size:
            continue

        projects = sorted({pr.project for pr in cohort_prs})
        created = sorted(pr.created for pr in cohort_prs)
        span_minutes = (created[-1] - created[0]).total_seconds() / 60.0
        window_start, window_end = created[0], created[-1]

        # Per-author project sets, for cohort overlap.
        by_author: dict[str, set[str]] = {}
        for pr in cohort_prs:
            by_author.setdefault(pr.author, set()).add(pr.project)
        overlaps = []
        author_lists = list(by_author.values())
        for i in range(len(author_lists)):
            for j in range(i + 1, len(author_lists)):
                a, b = author_lists[i], author_lists[j]
                overlaps.append(len(a & b) / max(1, len(a | b)))
        project_overlap = statistics.fmean(overlaps) if overlaps else 0.0

        ages = [pr.account_age_days for pr in cohort_prs]
        median_age = statistics.median(ages)
        trivial_rates = [triviality(pr) for pr in cohort_prs]
        mean_similarity = _measure(cohort_prs)["mean"]
        per_project_rate = len(cohort_prs) / max(1, len(projects))
        window = policy.campaign_window_minutes

        signals = {
            "similarity_density": round(mean_similarity, 3),
            "cohort_size": round(min(1.0, len(authors) / 10.0), 3),
            "project_overlap": round(project_overlap, 3),
            # PRs per hour inside the burst, relative to a 10/hour saturation point.
            "burstiness": round(
                min(1.0, (len(cohort_prs) / max(span_minutes / 60.0, 1e-9)) / 10.0), 3
            ),
            "account_newness": round(
                statistics.fmean([account_newness(a) for a in ages]), 3
            ),
            "triviality_rate": round(statistics.fmean(trivial_rates), 3),
        }
        fired = sum(1 for name, value in signals.items() if value >= 0.5)
        if fired < policy.min_campaign_signals:
            continue

        score = round(sum(WEIGHTS[k] * v for k, v in signals.items()), 3)

        sample_pairs = []
        for i, left in enumerate(cohort_prs[:40]):
            for right in cohort_prs[i + 1 : i + 6]:
                if left.author == right.author:
                    continue
                pair = len(shingles(left.text) & shingles(right.text)) / max(
                    1, len(shingles(left.text) | shingles(right.text))
                )
                if pair >= policy.similarity_threshold:
                    sample_pairs.append(
                        {
                            "a": left.pr_id,
                            "b": right.pr_id,
                            "projects": sorted({left.project, right.project}),
                            "jaccard": round(pair, 3),
                        }
                    )
            if len(sample_pairs) >= 5:
                break

        evidence = {
            "mean_pairwise_similarity": mean_similarity,
            "similarity_tier": "minhash+embedding" if tier2 else "minhash",
            "example_pairs": sample_pairs,
            "burst": (
                f"{len(cohort_prs)} PRs, {len(projects)} projects, "
                f"{int(span_minutes)} minute(s)"
            ),
            "triviality_rate": signals["triviality_rate"],
            "median_account_age_days": median_age,
            "signals_fired": fired,
            "signals": signals,
            "sample_prs": [pr.pr_id for pr in cohort_prs[:10]],
        }
        window_dict = {
            "start": window_start.isoformat().replace("+00:00", "Z"),
            "end": window_end.isoformat().replace("+00:00", "Z"),
            "minutes": int(span_minutes),
        }
        campaigns.append(
            Campaign(
                authors=authors,
                prs=cohort_prs,
                score=score,
                signals=signals,
                evidence=evidence,
                window=window_dict,
                affected_projects=projects,
                explanation=(
                    f"{len(authors)} accounts (median age {median_age:g} days) issued "
                    f"{len(cohort_prs)} near-identical pull requests to {len(projects)} "
                    f"projects within {int(span_minutes)} minutes. Mean payload "
                    f"similarity {mean_similarity:.2f}; triviality rate "
                    f"{signals['triviality_rate']:.2f}. {fired} of 6 independent "
                    f"signals fired."
                ),
            )
        )

    return sorted(campaigns, key=lambda c: c.score, reverse=True)
