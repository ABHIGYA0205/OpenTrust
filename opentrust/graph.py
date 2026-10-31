"""The trust graph: directed, weighted, asymmetric edges between projects.

Only *positive* statements become edges. Denouncements are not edges — they are
evidence that is weighted by the issuer's trust score (see :mod:`opentrust.reputation`).
Mixing negatives into the graph is how a single untrusted project poisons a network.
"""

from __future__ import annotations

from typing import Iterable

from .store import Network

__all__ = ["TrustGraph", "from_network"]


class TrustGraph:
    """Out-edge map: ``issuer -> {target_project -> weight}``."""

    def __init__(self, edges: dict[str, dict[str, float]] | None = None) -> None:
        self.edges: dict[str, dict[str, float]] = {}
        for src, targets in (edges or {}).items():
            for dst, weight in targets.items():
                self.add(src, dst, weight)

    def add(self, issuer: str, target: str, weight: float) -> None:
        if issuer == target:
            return
        self.edges.setdefault(issuer, {})[target] = float(weight)

    def nodes(self) -> set[str]:
        nodes: set[str] = set(self.edges)
        for targets in self.edges.values():
            nodes |= set(targets)
        return nodes

    def out_degree(self, node: str) -> int:
        return len(self.edges.get(node, {}))

    def trusted_by(self, node: str) -> dict[str, float]:
        return dict(self.edges.get(node, {}))

    def to_dict(self) -> dict[str, dict[str, float]]:
        return {src: dict(targets) for src, targets in self.edges.items()}

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"TrustGraph({len(self.nodes())} nodes, {sum(map(len, self.edges.values()))} edges)"


def from_network(network: Network, records: Iterable[dict] | None = None) -> TrustGraph:
    """Build the graph from ``trust_edge`` records.

    Later records from the same issuer about the same target win, so a project can
    revise its opinion without rewriting history.
    """
    graph = TrustGraph()
    latest: dict[tuple[str, str], tuple[str, float]] = {}
    for record in records if records is not None else network.of_type("trust_edge"):
        key = (record["issuer"], record["target_project"])
        issued = record.get("issued_at", "")
        if key not in latest or issued >= latest[key][0]:
            latest[key] = (issued, float(record["weight"]))
    for (issuer, target), (_, weight) in latest.items():
        graph.add(issuer, target, weight)
    return graph
