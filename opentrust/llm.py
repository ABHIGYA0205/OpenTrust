"""Local open-weight model integration (Ollama).

Two jobs, and only two:

1. Parse the free-text reason on a ``vouch`` or ``denounce`` record into structured
   ``scope`` labels and an ``evidence_strength`` score.
2. Draft the human-readable narrative for a campaign alert, from numbers the
   deterministic engines already computed.

Neither job can change a verdict. Trust propagation, reputation scoring and quarantine
decisions are deterministic over signed records; this module only produces *features*
and *explanations*. If no local model is reachable, every function falls back to a
deterministic keyword mapping — ``opentrust`` must never depend on a model to run.

No cloud API is ever contacted. Everything below talks to ``localhost``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field

__all__ = [
    "DEFAULT_MODEL",
    "ReasonAnalysis",
    "analyse_reason",
    "available",
    "narrate_campaign",
]

DEFAULT_MODEL = os.environ.get("TRUSTNET_MODEL", "qwen3:4b-instruct-2507-q4_K_M")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
TIMEOUT_SECONDS = 60

SCOPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "code_quality": (
        "code", "fix", "bug", "refactor", "test", "tests", "patch", "clean",
        "null", "dereference", "regression", "review", "merged",
    ),
    "security_review": (
        "security", "vulnerab", "cve", "exploit", "sanitis", "injection", "audit",
        "unsafe", "advisory", "traversal",
    ),
    "responsiveness": (
        "responsive", "quick", "replied", "communicat", "followed up", "prompt",
        "timely", "patient",
    ),
    "docs": ("doc", "readme", "typo", "wording", "guide", "tutorial", "comment"),
    "community": (
        "help", "mentor", "triaged", "triage", "answered", "welcom", "onboard",
        "community", "reviewed others",
    ),
}

EVIDENCE_STRONG = ("pull/", "issues/", "commit", "reproduced", "stack trace", "log", "cve-")
EVIDENCE_WEAK = ("low quality", "bad", "spam", "useless", "not good", "poor")


@dataclass
class ReasonAnalysis:
    scope: list[str]
    evidence_strength: float
    rationale: str
    source: str = "fallback"  # "llm" | "fallback"
    model: str | None = None
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "scope": self.scope,
            "evidence_strength": round(self.evidence_strength, 3),
            "rationale": self.rationale,
            "source": self.source,
            "model": self.model,
        }


# --------------------------------------------------------------------------- #
# Local model plumbing
# --------------------------------------------------------------------------- #


def available(model: str = DEFAULT_MODEL) -> bool:
    """True when a local Ollama server is reachable and has the model pulled."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=2) as response:
            tags = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return False
    names = {entry.get("name", "") for entry in tags.get("models", [])}
    return any(name == model or name.startswith(model.split(":")[0]) for name in names)


def _generate(prompt: str, model: str = DEFAULT_MODEL, temperature: float = 0.0) -> dict | None:
    """One strict-JSON completion from the local model. ``None`` on any failure."""
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature, "num_predict": 220},
        }
    ).encode()
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = json.loads(response.read())
        return json.loads(body.get("response", "") or "{}")
    except (urllib.error.URLError, OSError, ValueError, TimeoutError, json.JSONDecodeError):
        return None


PROMPT = """You classify the free-text reason attached to an open-source trust record.

Return ONLY JSON with this shape:
{{"scope": [<one or more of: code_quality, security_review, responsiveness, docs, community>],
  "evidence_strength": <0.0 to 1.0>,
  "rationale": "<one short sentence>"}}

evidence_strength means: how checkable is the claim in this text?
  0.0-0.3  vague opinion, no artefact referenced ("low quality contribution")
  0.4-0.6  a concrete claim but no reference
  0.7-1.0  names a pull request, issue, commit, reproduction or CVE

Record type: {kind}
Reason: {reason}

Examples:
Record type: vouch
Reason: Reviewed 3 merged PRs; caught a null-dereference we missed, with a regression test.
Answer: {{"scope": ["code_quality"], "evidence_strength": 0.6, "rationale": "Concrete engineering work described, no link included."}}

Record type: denounce
Reason: Low quality contribution.
Answer: {{"scope": [], "evidence_strength": 0.1, "rationale": "Bare opinion with no supporting artefact."}}
"""


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def analyse_reason(
    reason: str,
    kind: str = "vouch",
    use_llm: bool = True,
    model: str = DEFAULT_MODEL,
) -> ReasonAnalysis:
    """Structured meaning of a free-text vouch/denounce reason.

    Tries the local model first; on any failure returns the deterministic mapping.
    The ``source`` field always says which one produced the result, so a maintainer
    can tell whether a model was involved.
    """
    text = (reason or "").strip()
    if not text:
        return ReasonAnalysis(scope=[], evidence_strength=0.0, rationale="No reason given.")

    if use_llm:
        parsed = _generate(PROMPT.format(kind=kind, reason=text), model=model)
        if parsed:
            scope = [s for s in parsed.get("scope", []) if s in SCOPE_KEYWORDS]
            try:
                strength = max(0.0, min(1.0, float(parsed.get("evidence_strength", 0.0))))
            except (TypeError, ValueError):
                strength = 0.0
            return ReasonAnalysis(
                scope=scope or _fallback_scope(text),
                evidence_strength=strength,
                rationale=str(parsed.get("rationale", ""))[:200],
                source="llm",
                model=model,
                raw=parsed,
            )

    return _fallback_analysis(text)


def _fallback_scope(text: str) -> list[str]:
    lowered = text.lower()
    scopes = [name for name, words in SCOPE_KEYWORDS.items() if any(w in lowered for w in words)]
    return scopes or ["code_quality"]


def _fallback_analysis(text: str) -> ReasonAnalysis:
    lowered = text.lower()
    scope = _fallback_scope(text)

    strong = sum(1 for marker in EVIDENCE_STRONG if marker in lowered)
    weak = sum(1 for marker in EVIDENCE_WEAK if marker in lowered)
    strength = 0.5 + 0.2 * min(strong, 2) - 0.25 * min(weak, 2)
    strength = max(0.05, min(1.0, strength))

    if strong:
        rationale = "References a concrete artefact (link, reproduction, or advisory)."
    elif weak:
        rationale = "Opinion only: no artefact referenced."
    else:
        rationale = "Concrete claim without a referenced artefact."
    return ReasonAnalysis(
        scope=scope,
        evidence_strength=round(strength, 3),
        rationale=rationale,
        source="fallback",
        model=None,
    )


def narrate_campaign(evidence: dict, use_llm: bool = True, model: str = DEFAULT_MODEL) -> str:
    """Maintainer-readable incident narrative, from numbers only.

    The model may only restate values present in ``evidence``; if it is unavailable this
    returns the deterministic template produced by the campaign engine.
    """
    fallback = evidence.get("summary") or ""
    if not use_llm:
        return fallback
    prompt = (
        "Write a 3-sentence incident summary for an open-source maintainer, using ONLY "
        "the numbers given. Do not invent facts. Plain prose, no lists.\n\n"
        f"Numbers: {json.dumps(evidence, sort_keys=True)[:1500]}\n"
    )
    parsed = _generate(prompt, model=model, temperature=0.2)
    if not parsed:
        return fallback
    text = parsed.get("response") if isinstance(parsed, dict) else None
    return (text or fallback)[:1200]
