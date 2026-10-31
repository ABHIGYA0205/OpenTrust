"""Ed25519 records: signatures, tamper detection, hash-chained store."""

from __future__ import annotations

import json

import pytest

from opentrust import crypto, records
from opentrust.store import Store, load_project


def test_sign_and_verify_roundtrip():
    private, public = crypto.new_keypair()
    record = records.build_vouch(
        issuer="proj-a",
        subject="github:@alice",
        scope=["code_quality"],
        reason="Reviewed and merged 3 PRs.",
    )
    signed = crypto.sign_record(record, private)
    assert crypto.verify_record(signed, public)
    assert crypto.record_digest(signed) == crypto.record_digest(
        crypto.sign_record(record, private)
    )


def test_tampered_record_fails_verification():
    private, public = crypto.new_keypair()
    signed = crypto.sign_record(
        records.build_vouch(
            issuer="proj-a", subject="github:@alice", scope=["docs"], reason="ok"
        ),
        private,
    )
    tampered = dict(signed)
    tampered["subject"] = "github:@mallory"
    assert not crypto.verify_record(tampered, public)


def test_digest_ignores_signature_and_field_order():
    private, _ = crypto.new_keypair()
    record = records.build_denounce(
        issuer="proj-a",
        subject="github:@spam",
        reason="identical PRs",
        evidence=["https://example.com/pr/1"],
    )
    signed = crypto.sign_record(record, private)
    reordered = {k: signed[k] for k in reversed(list(signed))}
    assert crypto.record_digest(signed) == crypto.record_digest(reordered)


def test_store_is_append_only_and_chains(tmp_path):
    private, public = crypto.new_keypair()
    (tmp_path / "project.json").write_text(
        json.dumps({"id": "proj-a", "public_key": public})
    )
    store = Store(root=tmp_path, project_id="proj-a", private_key=private)
    first = store.append(
        records.build_trust_edge(issuer="proj-a", target_project="proj-b", weight=0.8)
    )
    second = store.append(
        records.build_trust_edge(issuer="proj-a", target_project="proj-c", weight=0.5)
    )
    assert "prev" not in first
    assert second["prev"] == crypto.record_digest(first)

    project = load_project(tmp_path)
    assert len(project.records) == 2
    assert project.report.rejected == 0


def test_reappending_the_same_content_extends_the_chain(tmp_path):
    private, public = crypto.new_keypair()
    (tmp_path / "project.json").write_text(
        json.dumps({"id": "proj-a", "public_key": public})
    )
    store = Store(root=tmp_path, project_id="proj-a", private_key=private)
    record = records.build_trust_edge(
        issuer="proj-a", target_project="proj-b", weight=0.7, issued_at="2026-10-31T20:00:00Z"
    )
    first = store.append(record)
    second = store.append(record)
    records_ = store.load()
    assert len(records_) == 2
    assert second["prev"] == crypto.record_digest(first)
    assert crypto.record_digest(first) != crypto.record_digest(second)


def test_denounce_requires_evidence():
    private, _ = crypto.new_keypair()
    bad = crypto.sign_record(
        records.build_denounce(
            issuer="proj-a", subject="github:@x", reason="bad", evidence=[]
        ),
        private,
    )
    with pytest.raises(records.RecordError):
        records.validate(bad)
