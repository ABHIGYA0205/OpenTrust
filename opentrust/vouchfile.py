"""Read and write Ghostty-style ``VOUCHED.td`` lists.

Vouch (https://github.com/mitchellh/vouch) keeps one flat file per project::

    # comment
    mitchellh                       vouched, platform defaults to GitHub
    github:someone Reviewed #120    vouched, with a note after the handle
    -badactor Submitted AI slop     denounced, with a reason

Ghostty's own list says it keeps denouncements "so other projects can slurp in our
list of denounced users if they trust us". That is the cross-project part OpenTrust
adds: importing turns each line into a signed record, so it can be verified and
weighted by how much the reader trusts the project it came from.

An imported line carries no evidence of its own, so its denouncements start as weak
evidence. The reputation layer treats them as allegations until someone corroborates
them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import crypto, llm, records
from .store import Project, Store

__all__ = ["Entry", "export_td", "import_td", "normalise_handle", "parse_td"]

URL = re.compile(r"https?://\S+")


@dataclass
class Entry:
    subject: str  # normalised, e.g. "github:@mitchellh"
    denounced: bool
    note: str
    line: int


def normalise_handle(raw: str) -> str:
    """``mitchellh`` / ``github:mitchellh`` / ``github:@mitchellh`` -> ``github:@mitchellh``."""
    platform, _, name = raw.rpartition(":")
    platform = (platform or "github").lower()
    return f"{platform}:@{name.lstrip('@')}"


def parse_td(text: str) -> list[Entry]:
    entries: list[Entry] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        handle, _, note = line.partition(" ")
        denounced = handle.startswith("-")
        handle = handle.lstrip("-")
        if not handle:
            continue
        entries.append(Entry(normalise_handle(handle), denounced, note.strip(), number))
    return entries


def _live_subjects(store_records: list[dict], kind: str) -> set[str]:
    retracted = {r["target"] for r in store_records if r.get("type") == "retract"}
    return {
        r["subject"]
        for r in store_records
        if r.get("type") == kind and crypto.record_digest(r) not in retracted
    }


def import_td(store: Store, text: str, source: str, use_llm: bool = True) -> dict[str, int]:
    """Sign every new line of a VOUCHED.td file into ``store``.

    Re-importing the same file adds nothing: subjects that already have a live
    record of the same kind are skipped.
    """
    existing = store.load()
    vouched = _live_subjects(existing, "vouch")
    denounced = _live_subjects(existing, "denounce")
    counts = {"vouch": 0, "denounce": 0, "skipped": 0}

    for entry in parse_td(text):
        if entry.subject in (denounced if entry.denounced else vouched):
            counts["skipped"] += 1
            continue
        kind = "denounce" if entry.denounced else "vouch"
        reason = entry.note or f"listed in {source} with no note"
        analysis = llm.analyse_reason(entry.note, kind=kind, use_llm=use_llm)
        origin = f"{source}#L{entry.line}"
        if entry.denounced:
            links = URL.findall(entry.note)
            record = records.build_denounce(
                issuer=store.project_id,
                subject=entry.subject,
                reason=reason,
                evidence=links or [origin],
                # No link means nobody can check it, so it starts at the lowest severity.
                severity="medium" if links else "low",
            )
            denounced.add(entry.subject)
        else:
            record = records.build_vouch(
                issuer=store.project_id,
                subject=entry.subject,
                scope=analysis.scope or ["community"],
                reason=reason,
                evidence=[origin],
            )
            vouched.add(entry.subject)
        record["evidence_strength"] = round(analysis.evidence_strength, 3)
        record["analysis_source"] = analysis.source
        record["imported_from"] = origin
        store.append(record)
        counts[kind] += 1
    return counts


def export_td(project: Project) -> str:
    """Render a project's live vouches and denouncements in Vouch's format."""
    retracted = {r["target"] for r in project.records if r.get("type") == "retract"}
    lines: dict[str, str] = {}
    for record in sorted(project.records, key=lambda r: r.get("issued_at", "")):
        if record.get("type") not in ("vouch", "denounce"):
            continue
        if crypto.record_digest(record) in retracted:
            continue
        handle = record["subject"].replace(":@", ":", 1)
        prefix = "-" if record["type"] == "denounce" else ""
        note = " ".join(str(record.get("reason", "")).split())
        lines[record["subject"]] = f"{prefix}{handle} {note}".rstrip()
    header = (
        f"# Vouch list exported by OpenTrust from project {project.id}.\n"
        "# Every line below is backed by a signed record in trust/records/.\n"
    )
    body = "\n".join(lines[s] for s in sorted(lines, key=lambda s: s.split(":@")[-1].lower()))
    return header + body + ("\n" if body else "")
