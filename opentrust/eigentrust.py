"""Personalised EigenTrust: how much should *this* project trust each peer?

Naive transitive trust (``max_depth=2`` closure) answers "reachable?", not "how
much". We instead run power iteration on the column-normalised trust matrix with a
teleport back to the viewing project:

    t(0)   = e_seed                                  start with total trust in myself
    t(k+1) = (1 - alpha) * C^T t(k) + alpha * e_seed  decay + teleport home

That gives a peer reached through three strong, well-trusted paths a high score and
a peer reached only through one dubious edge almost nothing — with no depth cutoff to
tune, and it stays stable as the network grows.
"""

from __future__ import annotations

import numpy as np

from .graph import TrustGraph

__all__ = ["limit_hops", "personal_trust", "top_trusted"]

DEFAULT_ALPHA = 0.15


def limit_hops(graph: TrustGraph, seed: str, max_hops: int | None) -> TrustGraph:
    """Restrict the graph to ``max_hops`` hops out from ``seed``.

    Depth 1 means "I see my direct peers' opinions, and nothing further". Depth 2 adds
    their peers, discounted by the decay term in :func:`personal_trust`.
    """
    if max_hops is None:
        return graph
    limited = TrustGraph()
    frontier = {seed}
    depth = 0
    while frontier and depth < max_hops:
        following: set[str] = set()
        for node in frontier:
            for target, weight in graph.edges.get(node, {}).items():
                limited.add(node, target, weight)
                following.add(target)
        frontier = following
        depth += 1
    return limited


def personal_trust(
    graph: TrustGraph,
    seed: str,
    alpha: float = DEFAULT_ALPHA,
    max_iter: int = 500,
    tol: float = 1e-12,
    max_hops: int | None = None,
) -> dict[str, float]:
    """Return ``{project_id: trust_weight}`` from ``seed``'s point of view."""
    graph = limit_hops(graph, seed, max_hops)
    nodes = sorted(graph.nodes() | {seed})
    if len(nodes) == 1:
        return {seed: 1.0}
    index = {node: i for i, node in enumerate(nodes)}
    n = len(nodes)

    matrix = np.zeros((n, n))
    for src, targets in graph.edges.items():
        for dst, weight in targets.items():
            if weight > 0:
                matrix[index[dst], index[src]] = float(weight)

    seed_vec = np.zeros(n)
    seed_vec[index[seed]] = 1.0

    # Column-stochastic. A project with no outgoing trust edges (a "dangling" node)
    # would leak probability mass, so it hands its mass back to the seed instead.
    for col in range(n):
        total = matrix[:, col].sum()
        if total > 0:
            matrix[:, col] /= total
        else:
            matrix[:, col] = seed_vec

    trust = seed_vec.copy()
    for _ in range(max_iter):
        # matrix holds C^T (rows = target, cols = source), so C^T @ t is matrix @ t.
        updated = (1.0 - alpha) * (matrix @ trust) + alpha * seed_vec
        if np.abs(updated - trust).sum() < tol:
            trust = updated
            break
        trust = updated

    return {nodes[i]: float(trust[i]) for i in range(n)}


def top_trusted(weights: dict[str, float], n: int = 10) -> list[tuple[str, float]]:
    return sorted(weights.items(), key=lambda kv: kv[1], reverse=True)[:n]
