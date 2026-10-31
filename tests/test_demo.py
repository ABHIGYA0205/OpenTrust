"""The live demo is part of the product, so CI runs it and checks each verdict.

Runs without Ollama in CI (deterministic fallback), and with both models locally.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("opentrust") is None, reason="needs `pip install -e .`")
def test_demo_tells_the_whole_story():
    result = subprocess.run(
        ["bash", str(ROOT / "demo.sh")],
        env={**os.environ, "DEMO_FAST": "1"},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout

    # One "== N." header per step, in order.
    headers = [line for line in out.splitlines() if line.lstrip("\x1b[1m").startswith("== ")]
    assert len(headers) == 9

    assert "signatures verified: 320 records, 0 rejected" in out
    assert "CAMPAIGN ALERT" in out
    assert "Verdict  : TRUSTED" in out  # @new-dev from proj-a
    assert "[denounce] proj-x (trust 0.000)" in out  # proj-x ignored by proj-a
    assert out.count("Verdict  : QUARANTINED") == 3  # proj-x's own view, slop-account, corroborated
    assert "which is not a rejection" in out  # unknown newcomer
    assert "Allegation: one uncorroborated denouncement" in out
    assert '"source": "fallback"' in out  # works with no model
