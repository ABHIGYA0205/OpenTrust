"""Vouch interop: Ghostty-style VOUCHED.td files in, signed records out, and back."""

from __future__ import annotations

import json
from pathlib import Path

from opentrust.cli import main
from opentrust.store import load_network
from opentrust.vouchfile import export_td, normalise_handle, parse_td

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "vouch"


def test_parse_follows_ghostty_syntax():
    entries = parse_td(
        "# comment\n\nmitchellh\ngithub:someone Reviewed #120\n-badactor Submitted AI slop\n"
    )
    assert [(e.subject, e.denounced, e.note, e.line) for e in entries] == [
        ("github:@mitchellh", False, "", 3),
        ("github:@someone", False, "Reviewed #120", 4),
        ("github:@badactor", True, "Submitted AI slop", 5),
    ]


def test_handles_normalise_to_one_form():
    assert normalise_handle("x") == normalise_handle("github:x") == normalise_handle("github:@x")
    assert normalise_handle("codeberg:x") == "codeberg:@x"


def _network(tmp_path: Path) -> Path:
    for project in ("proj-a", "proj-b", "proj-x"):
        assert main(["keygen", "--project", project, "--out", str(tmp_path / project)]) == 0
    assert main(["trust", "--project", "proj-a", "--out", str(tmp_path / "proj-a"),
                 "--target", "proj-b", "--weight", "0.9"]) == 0
    for project in ("proj-b", "proj-x"):
        assert main(["import-td", "--project", project, "--out", str(tmp_path / project),
                     "--file", str(EXAMPLES / f"{project}.VOUCHED.td"), "--no-llm"]) == 0
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"projects": [
        {"id": p, "path": p} for p in ("proj-a", "proj-b", "proj-x")
    ]}))
    return manifest


def test_imported_lists_are_signed_and_verify(tmp_path):
    network = load_network(_network(tmp_path))
    assert sum(p.report.rejected for p in network) == 0
    assert len(network.projects["proj-b"].of_type("vouch")) == 2
    assert len(network.projects["proj-b"].of_type("denounce")) == 1


def test_reimport_adds_nothing(tmp_path, capsys):
    _network(tmp_path)
    capsys.readouterr()
    assert main(["import-td", "--project", "proj-b", "--out", str(tmp_path / "proj-b"),
                 "--file", str(EXAMPLES / "proj-b.VOUCHED.td"), "--no-llm"]) == 0
    assert "vouches 0, denouncements 0, already present 3" in capsys.readouterr().out


def test_denouncement_without_a_link_starts_weak(tmp_path):
    network = load_network(_network(tmp_path))
    (record,) = network.projects["proj-x"].of_type("denounce")
    assert record["severity"] == "low"
    assert record["evidence"] == ["proj-x.VOUCHED.td#L2"]
    (linked,) = network.projects["proj-b"].of_type("denounce")
    assert linked["severity"] == "medium"
    assert linked["evidence"][0].startswith("https://")


def test_slide_scenario_from_vouch_files(tmp_path, capsys):
    """@new-dev is let in on proj-b's vouch; proj-x's denounce is ignored by proj-a."""
    manifest = _network(tmp_path)
    capsys.readouterr()
    assert main(["score", "--manifest", str(manifest), "--subject", "github:@new-dev",
                 "--viewer", "proj-a", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["verdict"] == "trusted"
    assert [i["issuer"] for i in result["ignored"]] == ["proj-x"]


def test_export_round_trips(tmp_path):
    network = load_network(_network(tmp_path))
    text = export_td(network.projects["proj-b"])
    again = {(e.subject, e.denounced) for e in parse_td(text)}
    assert again == {
        ("github:@new-dev", False),
        ("github:@steady-reviewer", False),
        ("github:@slop-account", True),
    }
