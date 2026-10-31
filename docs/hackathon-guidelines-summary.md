# Hacktoberfest 2026 — Hack Day Sonipat · Your Game Plan

**You build one thing, tonight, in 12 hours:** a working open-source AI tool that solves one of 8 maintainer problems, with open-weight models doing real work, shipped through a proper PR + CI workflow.

---

## 1. Hard deadlines (IST)

| When | What |
|---|---|
| **31 Oct, 6:30 PM** | Hackathon starts (now) |
| **31 Oct, 8:30 PM** | ⚠️ **Repo link submitted + HACKATHON.md as first commit** — no extension |
| 31 Oct, 7:30–9:30 PM | Dinner (eat, don't skip) |
| 31 Oct, 8:00 PM – 12:00 AM | Mentors available — Room 405, Learners' Lounge |
| 31 Oct, 11:00 PM – 1 Nov, 6:00 AM | Lock-in, floors 4 & 5 Block A. **No re-entry.** Carry meds, chargers, everything |
| **1 Nov, 6:30 AM** | **Repo freeze.** They fetch the repo at 6:30 AM — anything after doesn't exist |
| 1 Nov, 8:30 AM | Presentations: 8 min pitch + 4 min Q&A, 8 panels |
| 1 Nov, 1:30–2:00 PM | Results. Prizes: ₹25k / ₹15k / ₹10k (Problems 1–7), ₹5k (Gemma only) |

**Immediate priority: the repo exists and is submitted before 8:30 PM.** A brilliant repo submitted at 8:45 PM scores nothing.

---

## 2. The repo rules (this is ~25 of the 100 points, and free points)

```
your-repo/
├── HACKATHON.md                      ← FIRST commit, only this file
├── LICENSE                           ← MIT or Apache-2.0
├── README.md                         ← what it is, install, run
├── examples/                         ← sample input + REAL output your tool produced
│   ├── input/...
│   └── output/...
├── .github/
│   ├── pull_request_template.md      ← mandatory 4 headings (below)
│   └── workflows/ci.yml              ← installs deps + runs tests, must pass on final commit
├── src/ or package/
└── tests/
```

- **First commit = HACKATHON.md only.** Contains: team name, every member's name, chosen problem statement, **each model used + why**.
- **After that: PR-only on `main`.** No direct pushes. Every PR must pass CI. Solo? Merge your own.
- **Every PR names its models** — the open model your product uses in that change, *and* any AI coding assistant that helped (Copilot, Cursor, Claude Code are allowed — just disclose).
- **No secrets, no API keys, ever** in the repo.
- **Closed models score 0** on the 15-point Open-Source AI criterion (and can't even run on their test machines — no keys). Claiming a model you don't use = 0 **and −5 overall**.
- **Problem 8 zero-tolerance:** any cloud AI call, even once, disqualifies the team.

---

## 3. How you're scored (100)

**Automated, on the repo:**
- Functional correctness (~30) — features actually built, not stubs
- Open-source AI use (~15) — open-weight model doing meaningful work
- Testing & evidence (~10ish) — tests + `examples/` with real outputs
- Open-source workflow (10) — PRs, CI green

**Panel:**
- Live demo & usability
- Problem understanding
- Design & trade-offs (Q&A — any member can be asked *any* part of the code)

**Must pass gate:** public repo + MIT/Apache-2.0, and every member can explain the code. Judges will split your team and grill individuals.

---

## 4. The 8 problem statements, decoded

### Problems 1–7 (compete for top 3 cash prizes)

**P1 — Merges that know what's tested** *(Git internals)*
Build a Git tool that, during a backport/promote conflict, tells you for each side: where the change came from, whether CI/tests ever ran on it, whether it's live in PROD. Output must still be a **normal Git commit** any workflow can consume.
Judge test: real Django/CPython backport histories + their simulated DEV/UAT/PROD repos. Must handle code that was *modified* during cherry-pick (so `git cherry`/`patch-id` alone is not enough).
Hardest part: storing provenance that survives a fresh `git clone` (→ git notes / trailers / sidecar file pushed with the commit).

**P2 — Triage that tests the claims** *(GitHub App + sandboxed execution)*
Given an issue/PR, extract the individual **technical claims** ("crash on long URLs", "RCE in parse_url_v2()", "fixes #120"), and verify them: does the function even exist? reproduce in a sandbox? is the change covered by a test? Return an evidence-backed verdict with an explicit "uncertain".
Judge test: old closed issues of public repos labelled `invalid` / `cannot reproduce` / `confirmed` = ground truth.
Very buildable scoring win: a lot of "cannot reproduce" reports are refuted cheaply and provably (symbol doesn't exist, file doesn't exist, version predates the bug, no test touches the change). That's deterministic evidence, and the LLM only extracts/organises claims.

**P3 — Vulnerability reachability for Python** *(static analysis — the "govulncheck for Python" gap)*
For each alert from pip-audit/OSV, decide **reachable / not reachable / uncertain**, and show the **call path** as proof. Never say "safe" when unsure.
Judge test: small pinned Python apps, some calling the vulnerable function, some not.
The known trap: advisories rarely name the vulnerable function → you must diff the fixed vs vulnerable version to infer the vulnerable symbol, then trace calls with a real call graph (import/attribute resolution, and `getattr` = uncertain, not safe).

**P4 — Package ≈ source integrity** *(supply chain)*
Compare an npm/PyPI published tarball against its GitHub tag: classify every difference as expected build artifact vs suspicious (new postinstall script, obfuscated minified file that exists nowhere in the repo, extra file). Explain each difference, score risk, monitor new releases.
Judge test: real releases (mostly legit → false positives kill you) + organizer-tampered copies of those same packages (→ you must catch them).
Design must be rule/evidence-driven, not a hardcoded exception list.

**P5 — Docs drift** *(smallest scope, very demoable)*
PR renames `--timeout` → `--deadline`; the tool must point at `README.md` line 42 saying "Use --timeout to stop slow jobs" and link it to `cli.py` line 88, as a CI check that fails the PR.
Judge test: real project histories where docs were fixed *shortly after* the code change — can you flag the drift *before* the fix commit?
This is the most tractable in 12 hours: extract symbols/flags/defaults from the diff, grep docs for stale references, rank with a local LLM, emit precise line-level findings. Low false-positive design = win.

**P6 — Recover the decisions nobody wrote down** *(RAG over discussions)*
Mine issues/PRs/forums for decisions ("keep the C parser"), rejected alternatives ("rewrite in Rust"), and the reason ("2× slower on big files"). Link each to code (file + line range) and to its source discussion. When a new PR touches that code, surface the old decision.
Judge test: given PEP discussions **without** the PEP, recover what was rejected and why.
Needs a real retrieval + citation pipeline (every claim traceable to a comment URL). Embeddings must come from an open model.

**P7 — Trust network vs AI slop** *(graph + anomaly detection)*
Projects publish vouch/denounce lists; you choose whom *you* trust; trust propagates (A trusts B, B trusts C → how do you weigh C?), untrusted denouncements are ignored, and campaigns are caught (38 near-identical PRs from 3-day-old accounts hitting 40 projects in 2 hours) with evidence.
Judge test: simulated network of 20–50 projects, some vouches/denounces, a coordinated campaign, and legit newcomers who must **not** get blocked.
Most "cryptographic-ish" design freedom; scoring is flexible (they don't have one right answer), and it demos spectacularly (graph + campaign alert).

### Problem 8 — Gemma track (₹5,000, separate from top 3)

Build **anything original** where **Gemma does the core AI work, running on your own laptop**. Ollama / llama.cpp / LM Studio / transformers. Internet for GitHub/data is fine — **never** for the AI. No Gemini API, no fallback to any cloud model. A mentor will physically check `ollama ps` and your code hitting `localhost` during the night.

- `ollama pull gemma4:e4b` (most laptops), `gemma4:e2b` if RAM-limited. **Download it during dinner** — it's several GB.
- Same repo rules apply: HACKATHON.md, green CI, `examples/`, PRs.
- **You are ineligible for the ₹25k/15k/10k prizes.** That's the whole trade: a smaller prize pool for total freedom on the idea.
- In OrganizerHQ select **both** "Best Use of Gemma 4" and "Best Open-Source AI Project".

---

## 5. Which one should you pick?

Ranked by *(demoable in 12 h) × (scores well) ÷ (risk of a broken final commit)*:

1. **P5 Docs Drift** — tight scope, deterministic core, obvious demo, CI-native. Best expected score.
2. **P3 Reachability** — high ceiling, most respected technically, medium risk (call graphs on real code are fiddly). Fully offline: hand the LLM only the *symbol inference* step.
3. **P2 Triage** — best story ("we refute the claim with evidence"), needs a sandbox; keep execution isolated and timeboxed, and lean on static checks first.
4. **P7 Trust network** — most fun to demo, fuzzy rubric, easy to fake-tank with numbers. Good pick if your team likes graphs.
5. **P4 Package integrity** — strong, but tamper-detection needs many careful rules.
6. **P6 Decision recovery** — the best projects here need real IR work; RAG demos often look like "LLM summarises comments".
7. **P1 Git conflict provenance** — deepest Git work, worst time-to-first-working-demo. Only if someone already loves Git internals.
8. **P8 Gemma** — pick this **only** if your machine can run it and you have an idea you actually love, because you're giving up the main prize pool.

**Solo or small team? → P5.** Team of 3–4 with a security nerd? → P3. Want the fun demo? → P7. Laptop with a GPU and an idea? → P8.

---

## 6. Your next 90 minutes (before 8:30 PM)

1. **(10 min) Pick the problem.** Lock it. Every minute of debate costs build time.
2. **(5 min) Create an empty public repo** named after the project (no README/`.gitignore` auto-init).
3. **(10 min) First commit: `HACKATHON.md` only** → team name, members, problem, models + justification.
4. **(10 min) Add LICENSE (MIT/Apache-2.0), README stub, `.github/pull_request_template.md`, `.github/workflows/ci.yml`** — each as its own PR. This is where the 10 workflow points come from, and it's cheapest to do now, not at 5 AM.
5. **(5 min) Submit the repo link** on the OrganizerHQ form + select challenge "Best Open-Source AI Project".
6. **(10 min) Prove the model runs locally** — `ollama pull`, then a 10-line script that calls it. Commit that as a PR. Do this *early*; a model that won't load at 4 AM ends projects.
7. **Then build one vertical slice end-to-end**: input file → model call → JSON finding → printed evidence. Working and narrow beats broad and broken. Add `examples/` the moment that slice produces output.
8. **Reserve the last hour** for: README, `examples/` refresh, CI green on final commit, PR descriptions filled in. Do not code until 6:25 AM.

**Two failure modes that kill teams tonight:** (a) CI red on the final commit — you lose all automated correctness points; (b) building four features, finishing zero. Ship one thing that genuinely works and demo it honestly.
