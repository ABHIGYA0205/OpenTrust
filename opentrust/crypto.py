"""Ed25519 signing and canonical-JSON hashing for trust records.

Every record a project publishes is signed with that project's ed25519 key, so a
project is authoritative over its own statements and nothing else. Records are
hash-chained through the ``prev`` field, which makes each project's history
append-only and tamper-evident without any central server.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

__all__ = [
    "canonical_bytes",
    "new_keypair",
    "record_digest",
    "sign_record",
    "unsigned",
    "verify_record",
]


def canonical_bytes(obj: Any) -> bytes:
    """Deterministic serialisation. Required: signatures must be reproducible."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def unsigned(record: dict) -> dict:
    """Return the record without its signature (the part that gets signed)."""
    return {k: v for k, v in record.items() if k != "sig"}


def record_digest(record: dict) -> str:
    """Content address of a record, independent of its signature."""
    return "sha256:" + hashlib.sha256(canonical_bytes(unsigned(record))).hexdigest()


def new_keypair() -> tuple[str, str]:
    """Return ``(private_key_b64, public_key_b64)`` raw ed25519 key material."""
    sk = Ed25519PrivateKey.generate()
    priv = sk.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub = sk.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(priv).decode(), base64.b64encode(pub).decode()


def sign_record(record: dict, private_key_b64: str) -> dict:
    """Sign an unsigned record and return a new dict carrying ``sig``."""
    sk = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key_b64))
    body = unsigned(record)
    signature = sk.sign(canonical_bytes(body))
    signed = dict(body)
    signed["sig"] = base64.b64encode(signature).decode()
    return signed


def verify_record(record: dict, public_key_b64: str) -> bool:
    """Verify a record's signature. Returns False on any malformed input."""
    try:
        pk = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
        pk.verify(base64.b64decode(record["sig"]), canonical_bytes(unsigned(record)))
        return True
    except (InvalidSignature, KeyError, ValueError, TypeError):
        return False
