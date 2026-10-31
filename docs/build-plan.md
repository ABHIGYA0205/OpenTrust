# P7 · 3-Person Runbook — from now to 6:30 AM

Team of three, 12 hours, one repo, one problem. This file is the operating manual.
Design rationale lives in `p7-trust-network-design.md`; this is the *doing*.

---

## 0. Right now (next 25 minutes): get the repo submitted

The 8:30 PM deadline is the only thing that can zero you out. **`SUBMISSION-CHECKLIST.md`
is the compliance one-pager — keep it open.** Three separate 8:30 PM obligations:

1. First commit `HACKATHON.md` on `main`
2. **MLH check-in by every one of the three of you** — code **`6DMN96`**
3. Repo link submitted on MLH by the team leader, challenge **Best Open-Source AI Project**

And by **11:00 PM**: team created on **Cadence** (must match the MLH team exactly, no
switching after that). Wi-Fi is `RU_Guest` / `dev.club` / `dc`.

```bash
# in this workspace, already a git repo? no — initialise fresh:
cd /home/user
git init -b main
git config commit.template .gitmessage      # prompts for agent + models on every commit
git add HACKATHON.md && git commit -m "docs: team, problem statement, and AI models

Coding agent: <yours>
Models used in project: qwen3:4b-instruct-2507-q4_K_M, qwen3-embedding:0.6b"

# now create the GitHub repo (empty, public, no README, no .gitignore)
# then:
git remote add origin git@github.com:<you>/opentrust.git
git push -u origin main
```

**Before that push, edit `HACKATHON.md`:** team name, the three names, and the
"AI coding assistants" line. Nothing else.

Then open a second branch with everything else and make it your **first PR**:

```bash
git checkout -b feat/scaffold
git add -A && git commit -m "feat: trust network scaffold, CI, simulated network

Models: none in this change (deterministic core only).
AI assistants: <whatever you used>.
Tested: pytest -q (33 passing); tools/gen_network.py regenerates network/."
git push -u origin feat/scaffold
# open the PR on GitHub, fill in the template, wait for CI, merge
```

That single PR demonstrates the whole workflow the graders are looking for: PR template
filled, models named, CI green, `examples/` with real output. **Submit the repo link on
OrganizerHQ the moment `main` exists** — don't wait for the scaffold PR to merge.

While you do that, one of you starts `ollama pull qwen3:4b-instruct-2507-q4_K_M` and
`ollama pull qwen3-embedding:0.6b` (several GB — start now, it finishes while you work).

---

## 1. What you already have (so you don't rebuild it)

Working, tested, CI-green:

| Layer | Status |
| --- | --- |
| Ed25519 signing, canonical JSON, hash chain | ✅ done |
| Append-only store, network loading, signature verification | ✅ 320 records verified, 0 rejected |
| Trust graph + personalised EigenTrust | ✅ done |
| Reputation scoring: vouch / denounce / retract / expiry / recency / corroboration | ✅ done |
| 3-state verdicts with "unknown ≠ rejection" | ✅ done |
| MinHash Tier-1 similarity, LSH-free pairwise (fine at this scale) | ✅ done |
| Campaign detection: cohort clustering, 6 signals, evidence bundle | ✅ done |
| CLI: keygen, vouch, denounce, trust, sync, score, campaigns, report, graph | ✅ done |
| Generator: 40 projects, campaign with 30 identical + 8 paraphrased, 12 newcomers | ✅ done |
| Evaluate harness with the headline numbers | ✅ done |
| 33 tests, GitHub Actions CI | ✅ done |

**So your job is not "build opentrust". It is to make it defendable, beat the organisers'
fixtures, and demo well.** That is a much better place to spend 12 hours than hour four
of a crypto module.

---

## 2. Work split — one owner per module, so any of you can be grilled

The rule is "any member may be asked to explain any part". Clean ownership + a code
walkthrough at 5 AM is how you survive that.

### Person A — Trust & reputation (owns `graph.py`, `eigentrust.py`, `reputation.py`, `policy.py`)

Priority order:
1. **Policy published as a signed record** — `opentrust policy` command writing a
   `policy` record, and `policy_from_records` reading the latest per project. Right now
   the defaults are code constants; making them signed records is a visible,
   self-documenting win and it's ~40 lines.
2. **Scope semantics** — vouch for `docs` should not imply competence at `security_review`.
   You already have `scope_weights`; add a test proving a docs-only vouch contributes
   less than a security-review vouch from the same issuer.
3. **Denouncement DoS resistance** — a project that denounces everyone should lose
   credibility. Add a per-issuer denounce rate check: if an issuer has more than N
   denouncements with no corroboration, down-weight its later ones. Test it.
4. **Equivocation detection** — two peers holding different hashes for the same
   `(issuer, seq)` means that project published conflicting histories. Record it, report
   it in `sync`. This is the answer to "what stops a project rewriting its history?".

### Person B — Campaign intelligence (owns `signals.py`, `similarity.py`, `campaign.py`)

Priority order:
1. **Verify the AI deliverable on your own laptop.** `opentrust/llm.py` is written and
   wired into `vouch`/`denounce`/`analyse`, with a deterministic fallback. Your job is to
   run it with Ollama up and confirm `source: "llm"` comes back:
   `ollama pull qwen3:4b-instruct-2507-q4_K_M && opentrust analyse --reason "Reviewed 3 merged PRs, caught a null-deref"`
   Then add `analyse_reason` output to `examples/` (`--no-llm` and live) — that pair of
   files *is* the proof the model does real work. **15 points, and the −5 trap is that
   naming a model your code does not use.**
2. **Tier-2 embeddings** (already implemented in `similarity.py`); make `--tier2` measured:
   run `tools/evaluate.py --tier2` with Ollama up and put the delta in `examples/`.
   (30/30 vs 38/38 recall is a great slide.)
3. **Paraphrase-resistant Tier 1**: add a template skeleton signature — strip
   identifiers/numbers, hash the token-pattern — as a cheap second Tier-1 signal. It
   catches "same template, different words" without a model, which strengthens the
   `--no-llm` story.
4. **Campaign severity + affected-project fanout** in the alert record (already
   present), plus a `--since`/`--until` window so the demo can replay a time slice.

### Person C — Evidence, evaluation, and the pitch (owns `cli.py`, `explain.py`, `tools/`, `examples/`, `README.md`)

Priority order:
1. **An organiser-data adapter.** They will run your tool on *their* simulated network.
   Add `opentrust import --network DIR --format auto` that accepts a manifest-like
   directory, and a `--labels FILE` path to `tools/evaluate.py` so their ground truth
   feeds the same numbers. 40 lines that could decide your automated score.
2. **Metrics table regeneration** into `examples/evaluation.txt`, plus a `--json` mode so
   the numbers are quotable.
3. **Incident report** (`opentrust report --campaign`): markdown with the cohort table,
   example pairs, affected projects, and a timeline — the artefact a maintainer would
   actually receive. Have the local LLM write the narrative paragraph from the numbers.
4. **The Graphviz slide** — `examples/trust-graph.dot` already exists; render to SVG and
   put it on the demo slide. Colour nodes by trust weight, highlight the campaign cohort.
5. **Rehearse the demo 3 times.** You are the one who clicks.

---

## 3. Hour by hour

| Time | A (trust) | B (campaign + AI) | C (evidence + demo) |
| --- | --- | --- | --- |
| 8:30–9:00 | push scaffold, split branches | start model pulls | submit repo link |
| 9:00–10:30 | signed policy records | `llm.py` + scope parsing | organiser-data adapter |
| 10:30–12:00 | scope-weight tests, denounce-rate cap | wire LLM into vouch/denounce | `report --campaign` |
| **12:00** | **mentors leave — checkpoint: `main` green, demo runnable end to end** | | |
| 12:00–1:30 | equivocation detection | Tier-2 measured delta | metrics JSON + refresh `examples/` |
| 1:30–3:00 | policy tuning across 3 viewpoints | template-skeleton Tier 1 | graph SVG + slide numbers |
| 3:00–4:00 | **cross-review round 1** (A reviews B's module, etc.) | | |
| 4:00–5:00 | hardening: edge cases, empty network, single project | | test coverage for new code |
| 5:00–5:45 | **code walkthrough: each explains the other two's modules** | | |
| 5:45–6:15 | final PRs merged, CI green on final commit, PR descriptions complete | | |
| 6:15–6:30 | **freeze.** screenshot the green CI run | | |

Rule: **merge to `main` by 5:45 AM.** A PR that is open at 6:30 AM does not exist.

---

## 4. The 8-minute demo, shot by shot

Rehearse until it is muscle memory. Have a fallback: every command also has a captured
output in `examples/` in case the network dies.

1. **20 s — the hook.** "38 near-identical PRs. 40 projects. Two hours. Every maintainer
   saw one plausible PR. Nobody saw a campaign."
2. **90 s — the problem statement's own example.** Run
   `opentrust score --manifest network/manifest.json --subject "github:@new-dev" --viewer proj-a`
   → `TRUSTED`, "vouched by proj-b (trust 0.177)", and `proj-x` listed as **ignored,
   issuer trust 0.000 < 0.10**.
3. **60 s — the same records, a different verdict.** Re-run with `--viewer proj-x` →
   `QUARANTINED`. "No global truth. That's what decentralized means here."
4. **90 s — the campaign.** `opentrust campaigns --incoming network/incoming` → one alert:
   30 accounts, 30 projects, 107 minutes, similarity 1.00, 5 of 6 signals, example pairs
   with jaccard. Then `--tier2` with Ollama up to show the paraphrased 8 recovered.
5. **60 s — fairness.** `python tools/evaluate.py --network network` → *0 of 12 legitimate
   newcomers quarantined*. "Recall without that number is a spam filter that eats your
   community."
6. **60 s — how.** Ed25519 signed append-only records in each project's own git repo, no
   server, no consensus; personalised EigenTrust for propagation; two-tier similarity;
   deterministic verdicts, local models only for features and explanations.
7. **30 s — trade-offs.** Eventual consistency; no global consensus; equivocation
   detectable by gossip rather than prevented; precision over recall on quarantine;
   `unknown` never means blocked.

**Q&A ownership — know who answers what:**

| Question | Owner |
| --- | --- |
| Why EigenTrust and not transitive closure? Why does trust decay? | A |
| What if a project goes rogue and denounces everyone? | A |
| How does a brand-new contributor ever get in? | A |
| Why is AI-text detection insufficient? | B |
| What exactly does the model do, and what if it's wrong? | B |
| How do you avoid false positives at scale? | B |
| Why no blockchain? Where is the data stored? | C |
| What happens when two peers see different histories? | C |
| How would this work with 500 projects? | C |

---

## 5. Secrets and safety (an explicit rule, easy to break)

- `network/*/private.key` are synthetic fixture keys and are **gitignored**. Never commit
  them, never commit a real `.key`, never put anything in a `.env` you push.
- **Never post automated comments or issues to real repositories.** Everything runs on
  `network/` fixtures. This is in the participant guidelines and it is a hard fail.
- The evaluation environment has no API keys, and you use none: both models are local.

---

## 6. Definition of done at 6:30 AM

- [ ] `main` green on GitHub Actions on the final commit (screenshot it)
- [ ] Every change after the first commit arrived via PR, each with the template filled
- [ ] `HACKATHON.md` names the problem, all three members, both models, and why
- [ ] `examples/` has real outputs: score, campaign alert, evaluation numbers, graph
- [ ] `README.md` has install + run commands that work from a clean clone
- [ ] No secrets in the tree
- [ ] All three of you can run the demo command list and explain any module
- [ ] Repo submitted on **MLH**, challenge **Best Open-Source AI Project**, both
      teammates added to the submission
- [ ] All three members checked in on MLH with code `6DMN96`
- [ ] Team created on Cadence before 11:00 PM and matching the MLH team
- [ ] `git config commit.template .gitmessage` set, so agent + models appear on every
      commit (the guidelines require it on commits *and* PRs, not just PRs)

---

## 7. If you fall behind

Cut in this order, and never cut below the line:

1. Equivocation detection → drop.
2. Template-skeleton Tier 1 → drop.
3. Campaign incident report markdown → drop (the JSON alert carries the evidence).
4. Denounce-rate DoS resistance → simplify to a comment in the README.

**Never cut:** signing/verification, EigenTrust, the ignored-denouncement case, campaign
detection with evidence, the fairness number, `examples/`, green CI, and the freed
`unknown` state. Those are the rubric, line for line.
