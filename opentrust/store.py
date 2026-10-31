"""Append-only record storage, project loading and network sync.

Layout of one project in the network::

    proj-a/
      project.json                 {"id": "proj-a", "public_key": "..."}
      trust/records/<digest>.json  one signed record per file

Distribution is git: peers clone or pull each other's repositories and ingest the
record files. There is no server and no shared database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import crypto
from .records import RecordError, validate

__all__ = [
    "IngestReport",
    "Network",
    "Project",
    "Store",
    "load_network",
    "load_project",
]

RECORDS_DIRNAME = Path("trust") / "records"


@dataclass
class Store:
    """One project's private append-only log. Writes records; verifies on read."""

    root: Path
    project_id: str
    private_key: str

    @property
    def records_dir(self) -> Path:
        return Path(self.root) / RECORDS_DIRNAME

    def ensure(self) -> None:
        self.records_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[dict]:
        out: list[dict] = []
        if not self.records_dir.is_dir():
            return out
        for path in sorted(self.records_dir.glob("*.json")):
            out.append(json.loads(path.read_text()))
        return out

    def head_digest(self) -> str | None:
        """Digest of the most recent record, used as ``prev`` in the next one."""
        records = self.load()
        if not records:
            return None
        latest = max(records, key=lambda r: r.get("issued_at", ""))
        return crypto.record_digest(latest)

    def append(self, unsigned_record: dict) -> dict:
        """Chain, sign, validate and persist a record. Returns the signed record."""
        self.ensure()
        record = dict(unsigned_record)
        record.setdefault("issuer", self.project_id)
        record["issuer_key"] = self.public_key()
        head = self.head_digest()
        if head is not None:
            record["prev"] = head
        signed = crypto.sign_record(record, self.private_key)
        validate(signed)
        digest = crypto.record_digest(signed)
        path = self.records_dir / (digest.split(":", 1)[1] + ".json")
        if path.exists():  # idempotent: same content, same address
            return signed
        path.write_text(json.dumps(signed, indent=2, sort_keys=True) + "\n")
        return signed

    def public_key(self) -> str:
        manifest = Path(self.root) / "project.json"
        if manifest.is_file():
            return json.loads(manifest.read_text())["public_key"]
        raise FileNotFoundError(
            f"{manifest} missing; run `opentrust keygen --project {self.project_id} "
            f"--out {self.root}` first"
        )


@dataclass
class IngestReport:
    accepted: int = 0
    rejected: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return f"{self.accepted} accepted, {self.rejected} rejected"


@dataclass
class Project:
    id: str
    path: Path
    public_key: str
    records: list[dict] = field(default_factory=list)
    report: IngestReport = field(default_factory=IngestReport)

    def of_type(self, kind: str) -> list[dict]:
        return [r for r in self.records if r.get("type") == kind]


def load_project(path: str | Path) -> Project:
    """Load and signature-verify one project directory."""
    path = Path(path)
    manifest = path / "project.json"
    if not manifest.is_file():
        raise RecordError(f"{path} is not a project: project.json missing")
    meta: dict[str, Any] = json.loads(manifest.read_text())
    project = Project(id=meta["id"], path=path, public_key=meta["public_key"])
    records_dir = path / RECORDS_DIRNAME
    if not records_dir.is_dir():
        return project
    for record_path in sorted(records_dir.glob("*.json")):
        try:
            record = json.loads(record_path.read_text())
            if not crypto.verify_record(record, project.public_key):
                raise RecordError(f"bad signature in {record_path.name}")
            if record.get("issuer") != project.id:
                raise RecordError(
                    f"{record_path.name} claims issuer {record.get('issuer')!r}, "
                    f"expected {project.id!r}"
                )
            validate(record)
            project.records.append(record)
            project.report.accepted += 1
        except (RecordError, json.JSONDecodeError, KeyError) as exc:
            project.report.rejected += 1
            project.report.errors.append(f"{record_path.name}: {exc}")
    return project


@dataclass
class Network:
    projects: dict[str, Project] = field(default_factory=dict)

    def __iter__(self):
        return iter(self.projects.values())

    def records(self) -> list[dict]:
        out: list[dict] = []
        for project in self.projects.values():
            out.extend(project.records)
        return out

    def of_type(self, kind: str) -> list[dict]:
        return [r for r in self.records() if r.get("type") == kind]

    def project_ids(self) -> list[str]:
        return sorted(self.projects)


def load_network(manifest_path: str | Path) -> Network:
    """Load every project listed in a network manifest.

    ``manifest.json``::

        {"projects": [{"id": "proj-a", "path": "network/proj-a"}, ...]}
    """
    manifest_path = Path(manifest_path)
    data = json.loads(manifest_path.read_text())
    base = manifest_path.parent
    network = Network()
    for entry in data.get("projects", []):
        project_path = Path(entry["path"])
        if not project_path.is_absolute():
            project_path = base / project_path
        project = load_project(project_path)
        if entry.get("id") and project.id != entry["id"]:
            raise RecordError(
                f"manifest id {entry['id']!r} != project.json id {project.id!r}"
            )
        network.projects[project.id] = project
    return network


def iter_record_files(directory: str | Path) -> Iterable[Path]:
    yield from sorted(Path(directory).glob("*.json"))
