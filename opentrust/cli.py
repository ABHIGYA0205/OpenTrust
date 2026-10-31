"""opentrust command line interface.

    opentrust keygen   --project proj-a --out network/proj-a
    opentrust vouch    --project proj-a --out network/proj-a --subject github:@new-dev ...
    opentrust denounce --project proj-x --out network/proj-x --subject github:@new-dev ...
    opentrust trust    --project proj-a --out network/proj-a --target proj-b --weight 0.8
    opentrust sync     --manifest network/manifest.json
    opentrust score    --manifest network/manifest.json --subject github:@new-dev --viewer proj-a
    opentrust campaigns --incoming network/incoming --window 120 --min-cohort 5
    opentrust report   --manifest network/manifest.json --subject github:@new-dev --out out/report.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import crypto, llm, records
from .campaign import detect_campaigns
from .eigentrust import personal_trust, top_trusted
from .explain import render_campaign, render_network_summary, render_score
from .graph import from_network
from .policy import Policy, policy_from_records
from .reputation import score_subject
from .signals import PR
from .store import Store, load_network
from .similarity import embedding_similarity

__all__ = ["main"]


def _store(args: argparse.Namespace) -> Store:
    key_path = Path(args.out) / "private.key"
    if not key_path.is_file():
        sys.exit(
            f"no private key at {key_path}. Run: opentrust keygen --project "
            f"{args.project} --out {args.out}"
        )
    return Store(root=Path(args.out), project_id=args.project, private_key=key_path.read_text().strip())


def cmd_keygen(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "trust" / "records").mkdir(parents=True, exist_ok=True)
    private, public = crypto.new_keypair()
    (out / "project.json").write_text(
        json.dumps({"id": args.project, "public_key": public}, indent=2) + "\n"
    )
    key_path = out / "private.key"
    key_path.write_text(private + "\n")
    key_path.chmod(0o600)
    print(f"project {args.project!r} initialised at {out}")
    print(f"  public key : {public}")
    print(f"  private key: {key_path}  (never commit this file)")
    return 0


def cmd_vouch(args: argparse.Namespace) -> int:
    store = _store(args)
    analysis = llm.analyse_reason(args.reason, kind="vouch", use_llm=not args.no_llm)
    scope = args.scope or analysis.scope
    if not scope:
        sys.exit("could not determine scope; pass --scope explicitly")
    record = records.build_vouch(
        issuer=args.project,
        subject=args.subject,
        scope=scope,
        reason=args.reason,
        evidence=args.evidence or [],
    )
    record["evidence_strength"] = round(analysis.evidence_strength, 3)
    record["analysis_source"] = analysis.source
    signed = store.append(record)
    print(f"scope derived   : {', '.join(scope)}  "
          f"(evidence {analysis.evidence_strength:.2f}, via {analysis.source})")
    print(f"vouch recorded: {crypto.record_digest(signed)}")
    return 0


def cmd_denounce(args: argparse.Namespace) -> int:
    store = _store(args)
    analysis = llm.analyse_reason(args.reason, kind="denounce", use_llm=not args.no_llm)
    record = records.build_denounce(
        issuer=args.project,
        subject=args.subject,
        reason=args.reason,
        evidence=args.evidence or [],
        severity=args.severity,
    )
    record["evidence_strength"] = round(analysis.evidence_strength, 3)
    record["analysis_source"] = analysis.source
    signed = store.append(record)
    print(f"evidence strength: {analysis.evidence_strength:.2f} "
          f"({analysis.rationale}, via {analysis.source})")
    print(f"denounce recorded: {crypto.record_digest(signed)}")
    return 0


def cmd_trust(args: argparse.Namespace) -> int:
    store = _store(args)
    record = records.build_trust_edge(
        issuer=args.project, target_project=args.target, weight=args.weight
    )
    signed = store.append(record)
    print(f"trust edge {args.project} -> {args.target} ({args.weight}): "
          f"{crypto.record_digest(signed)}")
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    """Show which models the code actually uses, and whether they are live locally."""
    rows = [
        (
            llm.DEFAULT_MODEL,
            "opentrust/llm.py",
            "vouch/denounce reason -> structured scope + evidence strength",
            llm.available(llm.DEFAULT_MODEL),
        ),
        (
            "qwen3-embedding:0.6b",
            "opentrust/similarity.py",
            "Tier-2 paraphrased-PR similarity (campaign detection)",
            embedding_similarity(["probe a", "probe b"]) is not None,
        ),
    ]
    print("open-weight models used by this project (all local, no cloud APIs)")
    print("-" * 78)
    for name, module, job, live in rows:
        print(f"  {name:<22} {module:<26} {'LIVE' if live else 'not running'}")
        print(f"    job: {job}")
    print("-" * 78)
    if all(live for _, _, _, live in rows):
        print("both models reachable on localhost — no fallback in use")
    else:
        print("some models are not reachable: the deterministic fallback is used and")
        print("reported as source='fallback'. The product still runs. Start them with:")
        print(f"  ollama pull {llm.DEFAULT_MODEL} && ollama pull qwen3-embedding:0.6b")
    return 0


def cmd_analyse(args: argparse.Namespace) -> int:
    """Expose the model's one real job for demos and tests."""
    analysis = llm.analyse_reason(args.reason, kind=args.kind, use_llm=not args.no_llm)
    print(json.dumps(analysis.to_dict(), indent=2))
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    network = load_network(args.manifest)
    total_rejected = sum(p.report.rejected for p in network)
    print(render_network_summary(network))
    print()
    print(f"signatures verified: {sum(p.report.accepted for p in network)} records, "
          f"{total_rejected} rejected")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    network = load_network(args.manifest)
    policy = policy_from_records(network.records(), args.viewer)
    graph = from_network(network)
    weights = personal_trust(graph, seed=args.viewer, max_hops=policy.max_trust_hops)
    result = score_subject(
        network.records(), weights, policy, args.subject, viewer=args.viewer
    )
    if args.json:
        print(
            json.dumps(
                {
                    "subject": result.subject,
                    "viewer": result.viewer,
                    "verdict": result.verdict,
                    "score": round(result.score, 4),
                    "has_history": result.has_history,
                    "contributions": [
                        {
                            "kind": c.kind,
                            "issuer": c.issuer,
                            "issuer_trust": round(c.issuer_trust, 4),
                            "value": round(c.value, 4),
                            "detail": c.detail,
                        }
                        for c in result.contributions
                    ],
                    "ignored": [
                        {
                            "issuer": i.issuer,
                            "issuer_trust": round(i.issuer_trust, 4),
                            "why": i.why,
                        }
                        for i in result.ignored
                    ],
                },
                indent=2,
            )
        )
    else:
        print(render_score(result))
        print()
        print("trust weights as seen by " + args.viewer + ":")
        for node, weight in top_trusted(weights, 8):
            print(f"  {node:<14} {weight:.3f}")
    return 0


def _load_prs(directory: Path) -> list[PR]:
    prs: list[PR] = []
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text())
        items = data if isinstance(data, list) else [data]
        prs.extend(PR.from_dict(item) for item in items)
    return prs


def cmd_campaigns(args: argparse.Namespace) -> int:
    prs = _load_prs(Path(args.incoming))
    policy = Policy()
    if args.policy:
        policy = Policy.from_dict(json.loads(Path(args.policy).read_text()))
    policy.campaign_window_minutes = args.window
    policy.min_cohort_size = args.min_cohort

    campaigns = detect_campaigns(prs, policy, tier2=args.tier2)
    flagged = {pr.pr_id for campaign in campaigns for pr in campaign.prs}

    if args.json:
        print(
            json.dumps(
                {
                    "campaigns": [
                        {
                            "score": c.score,
                            "authors": c.authors,
                            "pr_ids": [pr.pr_id for pr in c.prs],
                            "affected_projects": c.affected_projects,
                            "window": c.window,
                            "signals": c.signals,
                            "explanation": c.explanation,
                        }
                        for c in campaigns
                    ],
                    "flagged_pr_ids": sorted(flagged),
                    "total_prs": len(prs),
                },
                indent=2,
            )
        )
    else:
        if not campaigns:
            print(f"no campaigns detected across {len(prs)} PRs")
        for campaign in campaigns:
            print(render_campaign(campaign))
            if args.narrate:
                text, source = llm.narrate_campaign(
                    llm.campaign_facts(campaign), fallback=campaign.explanation
                )
                via = llm.DEFAULT_MODEL if source == "llm" else "deterministic fallback"
                print(f"\nSummary for maintainers (via {via}, checked against the evidence):")
                print(f"  {text}")
            print()
        print(f"{len(prs)} PRs analysed, {len(flagged)} flagged across "
              f"{len(campaigns)} campaign(s)")
    return 0 if not campaigns else 1


def cmd_report(args: argparse.Namespace) -> int:
    network = load_network(args.manifest)
    policy = policy_from_records(network.records(), args.viewer)
    weights = personal_trust(from_network(network), seed=args.viewer, max_hops=policy.max_trust_hops)
    result = score_subject(
        network.records(), weights, policy, args.subject, viewer=args.viewer
    )
    text = render_score(result)
    tier2_note = ""
    if args.tier2:
        probe = embedding_similarity(["a", "b"])
        tier2_note = (
            "\n\nTier-2 embeddings: available"
            if probe is not None
            else "\n\nTier-2 embeddings: unavailable (no local model) — Tier 1 only"
        )
    body = f"# Contributor assessment\n\n```\n{text}\n```{tier2_note}\n"
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(body)
        print(f"report written to {args.out}")
    else:
        print(body)
    return 0


def cmd_network_graph(args: argparse.Namespace) -> int:
    """Emit the trust graph as DOT, for the demo slide."""
    network = load_network(args.manifest)
    graph = from_network(network)
    policy = policy_from_records(network.records(), args.viewer)
    weights = personal_trust(graph, seed=args.viewer, max_hops=policy.max_trust_hops)
    lines = ["digraph trust {", '  rankdir=LR;', '  node [shape=box, fontname="Helvetica"];']
    for src, targets in sorted(graph.edges.items()):
        for dst, weight in sorted(targets.items()):
            lines.append(
                f'  "{src}" -> "{dst}" [label="{weight:.2f}", penwidth={max(1.0, weight * 3):.1f}];'
            )
    lines.append("}")
    print("\n".join(lines))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="opentrust", description=__doc__.split("\n")[0])
    parser.add_argument("--version", action="version", version="opentrust 0.1.0")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("keygen", help="create a project identity")
    p.add_argument("--project", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_keygen)

    p = sub.add_parser("vouch", help="publish a scoped vouch")
    p.add_argument("--project", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--scope", nargs="+", help="derived by the local model when omitted")
    p.add_argument("--reason", required=True)
    p.add_argument("--evidence", nargs="*")
    p.add_argument("--no-llm", action="store_true", help="deterministic keyword mapping only")
    p.set_defaults(func=cmd_vouch)

    p = sub.add_parser("denounce", help="publish a denouncement (evidence required)")
    p.add_argument("--project", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--evidence", nargs="+", required=True)
    p.add_argument("--severity", choices=["low", "medium", "high"], default="medium")
    p.add_argument("--no-llm", action="store_true")
    p.set_defaults(func=cmd_denounce)

    p = sub.add_parser("trust", help="trust another project's judgement")
    p.add_argument("--project", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--weight", type=float, default=0.8)
    p.set_defaults(func=cmd_trust)

    p = sub.add_parser("models", help="show which open-weight models the code uses")
    p.set_defaults(func=cmd_models)

    p = sub.add_parser("analyse", help="parse a vouch/denounce reason into structured scope")
    p.add_argument("--reason", required=True)
    p.add_argument("--kind", choices=["vouch", "denounce"], default="vouch")
    p.add_argument("--no-llm", action="store_true")
    p.set_defaults(func=cmd_analyse)

    p = sub.add_parser("sync", help="load and verify a network")
    p.add_argument("--manifest", required=True)
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("score", help="assess one contributor from one viewpoint")
    p.add_argument("--manifest", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--viewer", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_score)

    p = sub.add_parser("campaigns", help="detect coordinated campaigns across projects")
    p.add_argument("--incoming", required=True)
    p.add_argument("--window", type=int, default=120, help="minutes")
    p.add_argument("--min-cohort", type=int, default=5)
    p.add_argument("--tier2", action="store_true", help="add local embedding similarity")
    p.add_argument("--policy")
    p.add_argument("--narrate", action="store_true",
                   help="add a plain-English summary from the local model, fact-checked")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_campaigns)

    p = sub.add_parser("report", help="write a markdown contributor report")
    p.add_argument("--manifest", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--viewer", required=True)
    p.add_argument("--out")
    p.add_argument("--tier2", action="store_true")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("graph", help="emit the trust graph as DOT")
    p.add_argument("--manifest", required=True)
    p.add_argument("--viewer", required=True)
    p.set_defaults(func=cmd_network_graph)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
