"""Per-PR signal extraction: the deterministic features campaign detection runs on.

Account age, triviality, target files and whether an issue is linked are cheap and
explainable. They are deliberately *behavioural*: we measure what an account did,
never whether its text looks machine-written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

__all__ = ["PR", "account_newness", "triviality"]

SAFE_PREFIXES = ("docs/", ".github/", "examples/", "README", "LICENSE")
SAFE_SUFFIXES = (".md", ".rst", ".txt", ".yml", ".yaml")
TRIVIAL_EXTENSIONS = SAFE_SUFFIXES


def _is_doc_path(path: str) -> bool:
    return path.startswith(SAFE_PREFIXES) or path.endswith(SAFE_SUFFIXES)


@dataclass
class PR:
    pr_id: str
    project: str
    author: str
    title: str
    body: str
    diff: str
    created_at: str
    account_age_days: int = 0
    files: list[str] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    linked_issue: bool = False
    includes_tests: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "PR":
        files = list(data.get("files", []))
        return cls(
            pr_id=data["pr_id"],
            project=data["project"],
            author=data["author"],
            title=data.get("title", ""),
            body=data.get("body", ""),
            diff=data.get("diff", ""),
            created_at=data["created_at"],
            account_age_days=int(data.get("account_age_days", 0)),
            files=files,
            additions=int(data.get("additions", len(data.get("diff", "").splitlines()))),
            deletions=int(data.get("deletions", 0)),
            linked_issue=bool(
                data.get("linked_issue", "#" in data.get("body", ""))
            ),
            includes_tests=bool(
                data.get(
                    "includes_tests",
                    any("test" in f.lower() for f in files),
                )
            ),
        )

    @property
    def text(self) -> str:
        """The payload we compare across projects."""
        return "\n".join([self.title, self.body, self.diff])

    @property
    def created(self) -> datetime:
        return datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))


def triviality(pr: PR) -> float:
    """0 = substantive change, 1 = the classic trivial-slop shape."""
    score = 0.0
    if pr.files and all(_is_doc_path(f) for f in pr.files):
        score += 0.4
    if not pr.linked_issue:
        score += 0.2
    if not pr.includes_tests:
        score += 0.15
    if pr.additions + pr.deletions <= 15:
        score += 0.25
    return round(min(1.0, score), 3)


def account_newness(account_age_days: int, fresh_days: int = 30) -> float:
    """1.0 for a brand-new account, decaying to 0.0 at ``fresh_days``."""
    if account_age_days >= fresh_days:
        return 0.0
    return round(1.0 - (account_age_days / fresh_days), 3)
