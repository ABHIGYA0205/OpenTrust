"""Generate a simulated trust network for development and evaluation.

Reproduces the evaluation scenario from the problem statement:

* 40 projects with their own keys, trust edges, vouches and denouncements
* one deliberately untrusted project (``proj-x``) that denounces a legitimate
  newcomer — the denouncement must carry no weight
* 12 legitimate newcomers with varied, plausible histories — none may be quarantined
* one coordinated campaign: 38 fresh accounts, a 2-hour burst across many projects,
  of which 30 send byte-identical payloads (Tier 1 catches them) and 8 send
  individually paraphrased payloads (only Tier 2 embeddings catch those)

Usage:
    python tools/gen_network.py --out network
    opentrust campaigns --incoming network/incoming
    opentrust score --manifest network/manifest.json --subject github:@new-dev --viewer proj-a

Private keys are written to ``<project>/private.key`` and are gitignored: they are
synthetic fixture keys, never real secrets, and never committed.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opentrust import crypto, records  # noqa: E402
from opentrust.store import Store  # noqa: E402

BASE_TIME = datetime(2026, 10, 31, 20, 0, tzinfo=timezone.utc)

CAMPAIGN_TITLE = "docs: improve wording in the installation section"

CAMPAIGN_BODY = (
    "This pull request improves the wording and readability of the installation "
    "section of the documentation. I noticed a few sentences that could be clearer for "
    "new contributors, so I rephrased them without changing any behaviour. No "
    "functional changes are included in this pull request and no tests were modified. "
    "Please let me know if you would like the wording adjusted, or if a changelog entry "
    "is required for documentation-only changes such as this one. Thank you for "
    "maintaining this project and for taking the time to review my contribution during "
    "the Hacktoberfest period."
)
CAMPAIGN_DIFF = "-installation: run pip install project\n+installation: use pip to install the project"

# Same intent, different words: shingling misses these, embeddings do not.
CAMPAIGN_PARAPHRASES = [
    (
        "docs: clearer install instructions",
        "The install part of the readme was a little confusing, so I tidied the "
        "sentences up. Nothing about how the code works has changed, and I did not "
        "touch any tests. Tell me if you want it worded differently. Thanks for "
        "looking after this repo.",
        "-installation: run pip install project\n+installation: install with pip",
    ),
    (
        "Reword the setup section of the docs",
        "I reworked the setup section so newcomers can follow it more easily. "
        "There are no behaviour changes here and no test updates. Happy to adjust the "
        "phrasing if you prefer. Appreciate the review during hacktoberfest.",
        "-installation: run pip install project\n+installation: pip install is enough",
    ),
    (
        "Documentation: tidy installation page",
        "Cleaning up the wording on the installation page. This is documentation only, "
        "with no functional changes and no new tests. Let me know if a changelog entry "
        "is needed. Thanks for maintaining the project and reviewing my change.",
        "-installation: run pip install project\n+installation: run the pip command",
    ),
    (
        "make the install docs friendlier",
        "The installation instructions were hard to read, so I made them friendlier. "
        "No code behaviour changed and no tests were touched. I can reword further if "
        "you like. Thanks for the time spent reviewing this during the event.",
        "-installation: run pip install project\n+installation: see the pip line below",
    ),
    (
        "docs: polish getting started text",
        "Polishing the text in the getting started guide so it reads better for new "
        "people. Documentation-only change, nothing functional, no tests modified. "
        "Happy to revise the wording. Thanks for maintaining and for the review.",
        "-installation: run pip install project\n+installation: use the pip command shown",
    ),
    (
        "Improve README installation wording",
        "The README's installation wording could be clearer, so I improved it. There "
        "are no behaviour differences and I did not change any tests. Let me know if "
        "you want different phrasing. Thank you for reviewing during hacktoberfest.",
        "-installation: run pip install project\n+installation: pip is all you need",
    ),
    (
        "docs(install): clearer sentences",
        "Making the sentences in the install docs clearer for newcomers. No functional "
        "changes and no test changes are part of this pull request. Happy to adjust if "
        "you would prefer other words. Thanks for maintaining this repository.",
        "-installation: run pip install project\n+installation: install via pip",
    ),
    (
        "Clarify the installation instructions",
        "Clarifying the installation instructions, which confused a few people. This "
        "touches documentation only, with no behaviour or test changes. Tell me if you "
        "want it phrased differently. Thanks for taking the time to review my work.",
        "-installation: run pip install project\n+installation: run pip as described",
    ),
]

LEGIT_TITLES = [
    "fix: handle empty config values",
    "feat: add retry with backoff to client",
    "fix: off-by-one in paginator",
    "refactor: split parser into modules",
    "fix: memory leak in worker pool",
    "test: cover timeout path",
    "feat: support TOML config",
    "perf: cache resolved imports",
    "fix: race in shutdown handler",
    "docs(api): document the new parameter",
    "fix: correct type annotation on loader",
    "feat: expose --profile flag",
]

LEGIT_BODIES = [
    "Fixes #{n}.\n\nI reproduced this on 2.4.1 by feeding an empty string to the loader. "
    "The guard was checking the wrong variable. Added a regression test that fails on "
    "the old code and passes now.",
    "Closes #{n}.\n\nMy benchmark took 4.2s on the 10k-row fixture; after the change it "
    "is 1.1s. I kept the change local to the resolver cache and added a test for the "
    "cache-miss path so the fast path is not the only one covered.",
    "Refs #{n}.\n\nSplit the 900-line parser into three modules with no behaviour change. "
    "The existing test suite passes unchanged, which is the proof that the refactor is "
    "behaviour-preserving.",
    "Fixes #{n}.\n\nThe worker pool was not joining on shutdown, so threads leaked on "
    "SIGTERM. Now it sets the stop event and joins with a timeout. Added a test that "
    "spawns and tears down the pool 50 times.",
    "Closes #{n}.\n\nAdds TOML loading behind the same interface as the YAML loader, with "
    "a shared conformance test run against both formats.",
]

LEGIT_DIFFS = [
    "-    if cfg is None:\n-        return cfg['value']\n+    if not cfg:\n"
    "+        raise ValueError('config value is required')\n+    return cfg['value']",
    "-    result = self._fetch(url)\n+    for attempt in range(self.retries):\n"
    "+        try:\n+            return self._fetch(url)\n"
    "+        except TransientError:\n+            sleep(2 ** attempt)\n+    raise TransientError(url)",
    "-    return items[start:start + self.page_size]\n+    end = min(start + self.page_size, len(items))\n"
    "+    return items[start:end]",
    "-class Parser:\n+class Tokenizer:\n+class NodeBuilder:\n+class Parser:",
    "-    while True:\n-        task = queue.get()\n+    while not self._stop.is_set():\n"
    "+        try:\n+            task = queue.get(timeout=0.1)\n+        except Empty:\n+            continue",
    "+def test_timeout_path(monkeypatch):\n+    monkeypatch.setattr(client, 'TIMEOUT', 0.01)\n"
    "+    with pytest.raises(TimeoutError):\n+        client.call('slow')",
    "+def load_toml(path):\n+    with open(path, 'rb') as handle:\n+        return tomllib.load(handle)",
    "-    return self._resolve(name)\n+    if name in self._cache:\n+        return self._cache[name]\n"
    "+    self._cache[name] = self._resolve(name)\n+    return self._cache[name]",
    "-    self._thread.start()\n+    self._thread = threading.Thread(target=self._run, daemon=True)\n+    self._thread.start()",
    "+    profile: bool = False,\n+    \"\"\"Emit per-stage timings to stderr.\"\"\"",
]

LEGIT_FILES = [
    ["src/loader.py", "tests/test_loader.py"],
    ["src/client.py", "tests/test_client.py"],
    ["src/paginator.py", "tests/test_paginator.py"],
    ["src/parser/core.py", "src/parser/nodes.py", "tests/test_parser.py"],
    ["src/pool.py", "tests/test_pool.py"],
    ["src/errors.py"],
]


def build_project(root: Path, project_id: str) -> dict:
    directory = root / project_id
    directory.mkdir(parents=True, exist_ok=True)
    private, public = crypto.new_keypair()
    (directory / "project.json").write_text(
        json.dumps({"id": project_id, "public_key": public}, indent=2) + "\n"
    )
    (directory / "private.key").write_text(private + "\n")
    store = Store(root=directory, project_id=project_id, private_key=private)
    store.ensure()
    return {"id": project_id, "dir": directory, "store": store}


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="network")
    parser.add_argument("--projects", type=int, default=40)
    parser.add_argument("--campaign-accounts", type=int, default=38)
    parser.add_argument("--newcomers", type=int, default=12)
    args = parser.parse_args()

    root = Path(args.out)
    incoming = root / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)

    n = args.projects
    ids = [f"proj-{chr(97 + i)}" if i < 26 else f"proj-{i}" for i in range(n)]
    projects = {pid: build_project(root, pid) for pid in ids}

    # --- trust edges ------------------------------------------------------
    # Everyone trusts 3 of the 4 hubs plus 2 peers, so trust reaches the whole
    # network but decays with distance. proj-a trusts proj-b explicitly: that is
    #   "Let in: vouched by Project B, which you trust."
    hubs = ids[:4]
    peers = [p for p in ids if p not in hubs and p != "proj-x"]
    for pid in ids:
        store = projects[pid]["store"]
        for hub in hubs:
            if hub == pid:
                continue
            store.append(
                records.build_trust_edge(
                    issuer=pid,
                    target_project=hub,
                    weight=round(rng.uniform(0.75, 0.95), 2),
                )
            )
        # A project trusts the few peers it actually works with. proj-a deliberately
        # keeps a small trust set, so its opinion of proj-b is strong.
        if pid != "proj-a":
            for peer in rng.sample(peers, k=2):
                store.append(
                    records.build_trust_edge(
                        issuer=pid,
                        target_project=peer,
                        weight=round(rng.uniform(0.3, 0.7), 2),
                    )
                )
    # proj-x is trusted by nobody: its opinions carry no weight for anyone else.
    projects["proj-x"]["store"].append(
        records.build_trust_edge(issuer="proj-x", target_project="proj-y", weight=0.2)
    )

    # --- vouches and denouncements ---------------------------------------
    legitimate = [
        "github:@alice",
        "github:@bruno",
        "github:@chen",
        "github:@divya",
        "github:@esme",
    ]
    for pid in ids:
        store = projects[pid]["store"]
        for subject in rng.sample(legitimate, k=2):
            store.append(
                records.build_vouch(
                    issuer=pid,
                    subject=subject,
                    scope=rng.choice(
                        [
                            ["code_quality"],
                            ["code_quality", "responsiveness"],
                            ["security_review"],
                            ["docs"],
                        ]
                    ),
                    reason=f"Reviewed {rng.randint(1, 6)} merged PRs; work was sound and tested.",
                    evidence=[f"https://github.com/{pid}/pull/{rng.randint(100, 400)}"],
                )
            )

    # proj-b vouches for @new-dev  -> the slide's "let in" case
    projects["proj-b"]["store"].append(
        records.build_vouch(
            issuer="proj-b",
            subject="github:@new-dev",
            scope=["code_quality"],
            reason="Fixed a real null-dereference and added the regression test.",
            evidence=["https://github.com/proj-b/pull/311"],
        )
    )
    # proj-x, trusted by nobody, denounces @new-dev -> the slide's "ignored" case
    projects["proj-x"]["store"].append(
        records.build_denounce(
            issuer="proj-x",
            subject="github:@new-dev",
            reason="Low quality contribution.",
            evidence=["https://github.com/proj-x/pull/9"],
            severity="high",
        )
    )
    # A genuinely bad actor, denounced by three trusted projects.
    for pid in ["proj-a", "proj-b", "proj-c"]:
        projects[pid]["store"].append(
            records.build_denounce(
                issuer=pid,
                subject="github:@slop-account",
                reason="Identical docs-only PR sent to dozens of projects in one hour.",
                evidence=[f"https://github.com/{pid}/pull/500"],
                severity="high",
            )
        )

    # --- incoming PRs: legitimate newcomers ------------------------------
    prs: list[dict] = []
    labels: dict[str, list[str]] = {"campaign": [], "campaign_paraphrased": [], "legit": []}
    for i in range(args.newcomers):
        prs.append(
            {
                "pr_id": f"pr_legit_{i:03d}",
                "project": rng.choice(ids),
                "author": f"github:@newcomer-{i + 1:02d}",
                "title": LEGIT_TITLES[i % len(LEGIT_TITLES)],
                "body": LEGIT_BODIES[i % len(LEGIT_BODIES)].format(n=100 + i * 7)
                + f"\n\nScope of this change: only `{LEGIT_FILES[i % len(LEGIT_FILES)][0]}`"
                + f", see report {i}.",
                "diff": LEGIT_DIFFS[i % len(LEGIT_DIFFS)],
                "created_at": iso(BASE_TIME + timedelta(minutes=rng.randint(0, 600))),
                "account_age_days": rng.choice([1, 3, 9, 14, 45, 200, 700]),
                "files": LEGIT_FILES[i % len(LEGIT_FILES)],
                "additions": rng.randint(18, 60),
                "deletions": rng.randint(2, 15),
                "linked_issue": True,
                "includes_tests": True,
                "label": "legit",
            }
        )

    # --- incoming PRs: the campaign --------------------------------------
    campaign_start = BASE_TIME + timedelta(minutes=180)
    identical = args.campaign_accounts - len(CAMPAIGN_PARAPHRASES)
    for i in range(args.campaign_accounts):
        project = ids[i % len(ids)]
        when = iso(campaign_start + timedelta(minutes=rng.randint(0, 118)))
        if i < identical:
            title, body, diff = CAMPAIGN_TITLE, CAMPAIGN_BODY, CAMPAIGN_DIFF
            label = "campaign"
        else:
            title, body, diff = CAMPAIGN_PARAPHRASES[i - identical]
            label = "campaign_paraphrased"
        prs.append(
            {
                "pr_id": f"pr_campaign_{i:03d}",
                "project": project,
                "author": f"github:@fresh-{i:02d}",
                "title": title,
                "body": body,
                "diff": diff,
                "created_at": when,
                "account_age_days": rng.randint(1, 4),
                "files": ["README.md"],
                "additions": rng.randint(1, 2),
                "deletions": rng.randint(1, 2),
                "linked_issue": False,
                "includes_tests": False,
                "label": label,
            }
        )

    rng.shuffle(prs)
    batch: list[dict] = []
    for i, pr in enumerate(prs):
        labels[pr["label"]].append(pr["pr_id"])
        batch.append({k: v for k, v in pr.items() if k != "label"})
        if len(batch) == 25:
            (incoming / f"batch_{i // 25:03d}.json").write_text(
                json.dumps(batch, indent=2) + "\n"
            )
            batch = []
    if batch:
        (incoming / f"batch_{len(prs) // 25:03d}.json").write_text(
            json.dumps(batch, indent=2) + "\n"
        )

    (root / "manifest.json").write_text(
        json.dumps({"projects": [{"id": pid, "path": pid} for pid in ids]}, indent=2) + "\n"
    )
    (root / "labels.json").write_text(json.dumps(labels, indent=2) + "\n")

    print(f"network written to {root}")
    print(f"  projects           : {len(ids)}")
    print(f"  incoming PRs       : {len(prs)}")
    print(f"    identical payloads : {len(labels['campaign'])}")
    print(f"    paraphrased payloads: {len(labels['campaign_paraphrased'])}  (Tier 2 only)")
    print(f"    legitimate         : {len(labels['legit'])}")
    print("  private keys       : <project>/private.key  (gitignored, never commit)")
    print()
    print("next:")
    print(f"  opentrust sync      --manifest {root}/manifest.json")
    print(f"  opentrust score     --manifest {root}/manifest.json "
          f"--subject github:@new-dev --viewer proj-a")
    print(f"  opentrust campaigns --incoming {root}/incoming")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
