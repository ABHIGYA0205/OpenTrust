"""Similarity: Tier-1 shingling must separate campaigns from real contributions."""

from __future__ import annotations

from opentrust.similarity import jaccard_estimate, minhash_signature, pairwise_similarity, shingles


def test_identical_texts_are_maximally_similar():
    text = "docs: fix typo in the installation section for new contributors"
    matrix = pairwise_similarity([text, text])
    assert matrix[0][1] > 0.95


def test_unrelated_texts_are_dissimilar():
    a = "fix: handle empty config values by raising ValueError in the parser"
    b = "docs: improve wording and readability of the contributing guide"
    assert pairwise_similarity([a, b])[0][1] < 0.2


def test_paraphrase_is_missed_by_shingles_but_caught_by_embeddings():
    """Documents the reason Tier 2 exists: shingles cannot see a rewrite."""
    a = "This pull request improves the wording of the installation section."
    b = "This PR makes the installation instructions easier to read."
    shingle_score = pairwise_similarity([a, b])[0][1]
    assert shingle_score < 0.6, "shingling should not be enough for a paraphrase"


def test_shingles_are_order_sensitive_unigrams_are_not():
    assert shingles("a b c d e f") != shingles("f e d c b a")


def test_empty_text_is_safe():
    signature = minhash_signature(shingles(""))
    assert jaccard_estimate(signature, signature) == 1.0
