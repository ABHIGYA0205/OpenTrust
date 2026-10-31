"""Two-tier pull-request similarity.

Tier 1 (always available) — MinHash over word shingles. Deterministic, explainable,
and fast. Catches exact and near-exact duplicate payloads.

Tier 2 (requires a local open-weight embedding model) — cosine similarity between
embeddings. Catches payloads that were *paraphrased* per repository, which shingling
cannot see. This is the concrete job our open model does; the delta between the two
tiers is measured and reported.
"""

from __future__ import annotations

import hashlib

__all__ = [
    "embedding_similarity",
    "jaccard_estimate",
    "minhash_signature",
    "pairwise_similarity",
    "shingles",
]

SHINGLE_SIZE = 5
NUM_PERM = 64


def _tokens(text: str) -> list[str]:
    return text.lower().split()


def shingles(text: str, k: int = SHINGLE_SIZE) -> set[str]:
    tokens = _tokens(text)
    if len(tokens) < k:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)}


def _hash(token: str, seed: int) -> int:
    return int.from_bytes(
        hashlib.blake2b(token.encode("utf-8"), digest_size=8, key=str(seed).encode()).digest(),
        "big",
    )


def minhash_signature(shingle_set: set[str], num_perm: int = NUM_PERM) -> tuple[int, ...]:
    if not shingle_set:
        return tuple(0 for _ in range(num_perm))
    return tuple(
        min(_hash(shingle, seed) for shingle in shingle_set)
        for seed in range(num_perm)
    )


def jaccard_estimate(sig_a: tuple[int, ...], sig_b: tuple[int, ...]) -> float:
    """MinHash estimate of Jaccard similarity between two shingle sets."""
    if not sig_a or not sig_b or len(sig_a) != len(sig_b):
        return 0.0
    same = sum(1 for a, b in zip(sig_a, sig_b) if a == b)
    return same / len(sig_a)


def pairwise_similarity(texts: list[str], num_perm: int = NUM_PERM) -> list[list[float]]:
    """Symmetric matrix of Tier-1 similarity estimates."""
    signatures = [minhash_signature(shingles(t), num_perm) for t in texts]
    n = len(texts)
    matrix = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            value = jaccard_estimate(signatures[i], signatures[j])
            matrix[i][j] = matrix[j][i] = value
    return matrix


# Qwen3-Embedding is trained to take a task instruction in front of the text.
# Asking it to match on what a change does, not how it is worded, is what lets it
# see through a reworded spam payload.
PR_INSTRUCTION = (
    "Given a pull request, find other pull requests that make the same change, "
    "however they are worded"
)


def embedding_similarity(
    texts: list[str],
    model: str = "qwen3-embedding:0.6b",
    instruction: str | None = None,
) -> list[list[float]] | None:
    """Tier-2 similarity via a local Ollama embedding model.

    Returns ``None`` when no local model is reachable, so callers can fall back to
    Tier 1 instead of failing. Never calls a cloud API.
    """
    if instruction:
        texts = [f"Instruct: {instruction}\nQuery: {text}" for text in texts]
    try:
        import json
        import urllib.request

        vectors = []
        for text in texts:
            request = urllib.request.Request(
                "http://localhost:11434/api/embeddings",
                data=json.dumps({"model": model, "prompt": text}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                vectors.append(json.loads(response.read())["embedding"])
    except Exception:  # model server not reachable / model not pulled
        return None

    def cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0

    n = len(vectors)
    return [
        [1.0 if i == j else cosine(vectors[i], vectors[j]) for j in range(n)]
        for i in range(n)
    ]
