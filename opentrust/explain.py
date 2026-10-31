"""Human-readable rendering of verdicts and campaign alerts.

Numbers come from the deterministic engines; this module only formats them. Optional
LLM narration is wired in ``cli.py`` behind ``--narrate`` and never changes a verdict.
"""

from __future__ import annotations

from .campaign import Campaign
from .reputation import SubjectScore

__all__ = ["render_campaign", "render_network_summary", "render_score"]


def render_score(score: SubjectScore) -> str:
    return score.explain()


def render_campaign(campaign: Campaign) -> str:
    lines = [
        "CAMPAIGN ALERT",
        f"  score          : {campaign.score:.2f}",
        f"  cohort         : {len(campaign.authors)} accounts, "
        f"{len(campaign.prs)} PRs, {len(campaign.affected_projects)} projects",
        f"  window         : {campaign.window['start']} -> {campaign.window['end']} "
        f"({campaign.window['minutes']} min)",
        f"  similarity     : {campaign.evidence['mean_pairwise_similarity']:.2f} "
        f"({campaign.evidence['similarity_tier']})",
        f"  account age    : median {campaign.evidence['median_account_age_days']:g} days",
        f"  triviality     : {campaign.evidence['triviality_rate']:.2f}",
        "",
        "  signals:",
    ]
    for name, value in campaign.signals.items():
        bar = "#" * int(value * 20)
        lines.append(f"    {name:<20} {value:.2f} {bar}")
    lines += ["", "  example near-identical pairs:"]
    for pair in campaign.evidence["example_pairs"][:5]:
        lines.append(
            f"    {pair['a']} ~ {pair['b']}  jaccard {pair['jaccard']:.2f}  "
            f"({', '.join(pair['projects'])})"
        )
    lines += ["", f"  projects affected: {', '.join(campaign.affected_projects[:12])}"]
    lines += ["", f"  {campaign.explanation}"]
    return "\n".join(lines)


def render_network_summary(network, trust_weights: dict[str, float] | None = None) -> str:
    lines = [f"network: {len(network.projects)} projects", ""]
    header = f"  {'project':<14} {'records':>8} {'vouch':>6} {'denounce':>9} {'edges':>6}"
    if trust_weights is not None:
        header += f" {'trust':>7}"
    lines.append(header)
    for project in sorted(network.projects.values(), key=lambda p: p.id):
        row = (
            f"  {project.id:<14} {len(project.records):>8} "
            f"{len(project.of_type('vouch')):>6} "
            f"{len(project.of_type('denounce')):>9} "
            f"{len(project.of_type('trust_edge')):>6}"
        )
        if trust_weights is not None:
            row += f" {trust_weights.get(project.id, 0.0):>7.3f}"
        lines.append(row)
        for error in project.report.errors[:2]:
            lines.append(f"      ! rejected: {error}")
    return "\n".join(lines)
