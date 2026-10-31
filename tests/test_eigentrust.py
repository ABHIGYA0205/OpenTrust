"""Trust propagation: personalised EigenTrust behaviour."""

from __future__ import annotations

import pytest

from opentrust.eigentrust import personal_trust
from opentrust.graph import TrustGraph


def test_seed_trusts_itself_most():
    graph = TrustGraph({"a": {"b": 0.9}})
    weights = personal_trust(graph, seed="a")
    assert weights["a"] > weights["b"]


def test_direct_trusted_edge_beats_untrusted_neighbour():
    graph = TrustGraph(
        {
            "a": {"b": 0.9},
            "c": {"b": 0.9, "a": 0.9},
        }
    )
    weights = personal_trust(graph, seed="a")
    assert weights["b"] > weights["c"]
    assert weights["c"] == pytest.approx(0.0, abs=1e-9)


def test_trust_propagates_two_hops_with_decay():
    """a -> b -> c: c is reachable, but worth less than b."""
    graph = TrustGraph({"a": {"b": 1.0}, "b": {"c": 1.0}})
    weights = personal_trust(graph, seed="a")
    assert weights["c"] > 0
    assert weights["c"] < weights["b"]


def test_untrusted_isolate_gets_no_weight():
    """proj-x trusts someone, but nobody trusts proj-x: it carries no weight."""
    graph = TrustGraph(
        {
            "a": {"b": 0.9},
            "b": {"a": 0.8},
            "x": {"y": 0.2},
            "y": {"x": 0.2},
        }
    )
    weights = personal_trust(graph, seed="a")
    assert weights["x"] == pytest.approx(0.0, abs=1e-9)
    assert weights["y"] == pytest.approx(0.0, abs=1e-9)


def test_weights_are_viewpoint_dependent():
    graph = TrustGraph({"a": {"b": 0.9}, "c": {"d": 0.9}})
    from_a = personal_trust(graph, seed="a")
    from_c = personal_trust(graph, seed="c")
    assert from_a["b"] > from_a["d"]
    assert from_c["d"] > from_c["b"]


def test_strong_path_beats_single_weak_edge():
    """Two strong chains into 'target' should outweigh one weak direct edge."""
    graph = TrustGraph(
        {
            "a": {"mid1": 1.0, "mid2": 1.0},
            "mid1": {"target": 1.0},
            "mid2": {"target": 1.0},
            "b": {"target2": 0.05},
            "a_trusted_weak": {"target2": 1.0},
            "a2": {"a_trusted_weak": 1.0},
        }
    )
    weights = personal_trust(graph, seed="a")
    assert weights["target"] > 0
    assert weights["a_trusted_weak"] == pytest.approx(0.0, abs=1e-9)
