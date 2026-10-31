# P7 — Decentralized Trust Network for Open Source Contributions · Build Plan

> "You build: projects share whom they vouch for, choose whom they trust, and catch spam campaigns early."

Your tool must do **three** things at once, and they pull in opposite directions:

1. **Individual fairness** — evaluate one new contributor, without gatekeeping honest newcomers.
2. **Network-level correlation** — see a campaign that is invisible to any single maintainer.
3. **No central authority** — no server, no database, no shared API that everyone must trust.

Get only #1 → a reputation score nobody needs. Get only #2 → a spam classifier that bans newcomers. Get only #3 → a crypto demo with no decisions in it. The score is in the combination.

---

## 1. What is actually being scored

Organizers will hand you (or simulate for you) a network of **20–50 projects** containing:
- existing **vouch** lists
- existing **denounce** lists
- **incoming PRs**
- **one coordinated spam campaign** (the slide's shape: ~38 near-identical PRs, 3-day-old accounts, 40 projects, 2-hour window)
- **legitimate newcomers** with no established reputation

You're scored on: campaign caught (with evidence) **and** honest newcomers not excluded. Those two numbers together are your headline. Any team can maximise one of them.

Key technical considerations from the doc, translated into design decisions:

| They ask | Your answer |
|---|---|
| A trusts B, B trusts C — how does A weigh C's members? | Trust propagation with decay: **personalised EigenTrust / PageRank** from A's node, not a depth-cutoff closure |
| How does trust propagate? | Directed, weighted, asymmetric edges; multiplicative decay per hop; recomputed from *your* viewpoint |
| How to stop malicious denouncements harming contributors? | Only denouncements from sufficiently-trusted issuers count; below threshold they're quarantined, not applied; corroboration weighted; append-only retractions |
| How do legitimate newcomers establish trust? | Three states (`trusted`/`unknown`/`quarantined`), a green path for unknowns, bootstrapping via micro-contributions and any trusted vouch |
| How does the network stay decentralized? | Signed records in each project's own git repo; git as the transport; **no consensus needed**, no central service |
| Why is AI-text detection alone insufficient? | Slop is a *coordination* phenomenon, not a textual one — see §6 |

---

## 2. Data model: signed append-only records

This is the foundation. Get it right and everything else is computation; get it wrong and you spend the night patching.

**Project identity = an Ed25519 keypair.** Not a GitHub org name (forgeable), not a database row (central). Each project signs its own statements. Canonical JSON serialisation (sorted keys, no whitespace, UTF-8) → hash → sign.

```json
{
  "type": "vouch",
  "issuer": "proj-b",                    // project id
  "issuer_key": "ed25519:9f3a…",
  "subject": "github:@new-dev",
  "scope": ["code_quality", "responsiveness"],   // what exactly is vouched for
  "reason": "Reviewed 2 real bug fixes; caught a null-deref we missed.",
  "evidence": ["https://github.com/proj-b/pull/311"],
  "issued_at": "2026-10-31T19:12:00Z",
  "expires_at": "2027-10-31T19:12:00Z",
  "nonce": "7c1e…",
  "prev": "sha256:…",                    // hash of this issuer's previous record
  "sig": "ed25519:…"
}
```

Record types:

| type | purpose |
|---|---|
| `vouch` | positive claim about a subject, scoped, with evidence + expiry |
| `denounce` | negative claim, **requires evidence[]**, severity, and a stated reason |
| `retract` | withdraw a previous record by hash — append-only correction, never deletion |
| `trust_edge` | "I trust project X's judgement, weight 0.8" — directed, asymmetric |
| `campaign_alert` | network-level finding, evidence bundle, signed by the detecting project |
| `policy` | your thresholds (min trust, corroboration, windows) — published, so your judgements are auditable |

Why `prev` + signatures: each project's records form a **hash chain** (a mini transparency log, Scuttlebutt-style). Cheap to verify, tamper-evident, and it gives you a real answer when a judge asks "what stops a project rewriting its own history?" — nothing stops them rewriting *their own*, but peers who already hold the old hashes can detect equivocation and flag it.

**Where it lives:**
```
proj-b/trust/records/0001.json … NNNN.json     ← in that project's own git repo
proj-b/trust/pubkey.pem
network.json                                    ← manifest: list of peer repos/paths
```
Distribution = `git clone`/`git pull`. That's the whole decentralization story: no server, no database, no API keys, and any project can leave the network taking its records with it.

---

## 3. Trust computation

### 3.1 The graph

- Nodes = projects (and optionally subjects).
- Edges = `trust_edge` records: directed, weight ∈ (0,1].
- **Only positive edges.** Denouncements are not edges; they're payload evaluated *subject to* trust weight. Mixing them into the graph is the most common mistake and it lets an untrusted node poison your scores.

### 3.2 The algorithm — personalised EigenTrust

EigenTrust (Kamvar et al., designed exactly for P2P reputation) = power iteration on the trust matrix, seeded from **you**:

```
t⁽⁰⁾ = e_me                         # start all trust at my own node
t⁽ᵏ⁺¹⁾ = (1-α)·Cᵀ·t⁽ᵏ⁾ + α·e_me   # α = 0.15 teleport back to me
repeat until ‖t⁽ᵏ⁺¹⁾ − t⁽ᵏ⁾‖₁ < ε
```

`C` = column-normalised trust matrix. Result: `trust_in_project[i]` = how much *I* should believe project `i`, at 1–3 hops, decaying naturally.

**Why this and not `max_depth=2` closure:** the closure gives you a flat "reachable in 2 hops" boolean with no notion of how many weak paths exist. EigenTrust gives you 0.71 for a well-connected-trusted project and 0.04 for one hung off a single dubious edge — and if you're the only project that trusts a sketchy node, its weight collapses to ~α·(its share). It also degrades gracefully as the network grows, which matters because they'll test with 20–50 projects, possibly more. Say this in Q&A; it's a visible depth marker.

Implementation: pure numpy, ~40 lines, converges in <50 iterations at this scale. Include a unit test that a 2-hop chain beats a 1-hop edge from an untrusted seed.

### 3.3 From trust weights to a subject's reputation

```
score(subject) = Σ over vouch records v:
                    trust_in_project[v.issuer] · scope_weight(v.scope) · recency(v.issued_at)
              −  Σ over denounce records d, only where trust_in_project[d.issuer] ≥ τ_denounce:
                    trust_in_project[d.issuer] · severity(d) · corroboration(d)
```

- `corroboration(d)` = 1 + log(1 + number of *independent* trusted issuers who also denounce the subject). One hostile project can move a contributor by at most its own weight — which, if you don't trust it, is ~0. **That is the prompt's example, satisfied structurally** ("X's denounce is ignored: you don't trust X").
- `recency`: exponential decay, half-life ~180 days.
- **Retractions** zero out the original record's contribution before scoring. Never mutate, just recompute.

Verdict mapping (per your published `policy`):
- `trusted` — score above τ_trusted
- `unknown` — between τ_quarantine and τ_trusted, **or no data at all** (this is the default for a first-time contributor, and it is *not* a rejection)
- `quarantined` — below τ_quarantine **or** linked to a confirmed campaign

---

## 4. Campaign detection — the actual innovation

Individual reputation can't see a campaign. This stage looks at the **network-wide contribution stream** and finds coordination.

### 4.1 Per-PR signal extraction (deterministic, explainable)

```python
@dataclass
class ContributionSignal:
    pr_id: str; project: str; author: str; author_account_age_days: int
    title: str; body: str; diff_text: str
    files_touched: list[str]; additions: int; deletions: int
    linked_issue: bool; includes_tests: bool
    created_at: datetime
```

Derived features:
- `account_age_days` (3-day-old accounts are the slide's tell)
- `triviality`: tiny diff, docs/whitespace/`.github/` only, no linked issue, no tests
- `target_set`: which projects this author hit
- `path_entropy`: how uniform the target file is across their PRs

### 4.2 Two-tier similarity — this is where the open model earns its points

- **Tier 1, MinHash + LSH** over 5-gram token shingles of title+body+diff. Deterministic, O(n) with banding, catches exact and near duplicates at 0.9+ Jaccard. Fast enough for hundreds of PRs.
- **Tier 2, open-weight embeddings** (`nomic-embed-text` via Ollama): cosine ≥ 0.85 catches **paraphrased** slop that shingles miss — the same generated blurb reworded per repo. This is genuinely necessary, not decorative, and it's the honest answer to "why does your model matter?"

Keep both, report which tier fired. That distinction is a great slide: "Tier 1 found 31 duplicates; Tier 2 found 7 more that were reworded."

### 4.3 Coordination signals (graph over authors × projects × time)

1. **Burstiness** — PR count into the network per (author, project) in a sliding window. Flag windows where ≥K projects receive PRs from the same cohort within T (the stated case: 40 projects in 2 hours).
2. **Cohort clustering** — build a bipartite author↔project graph over the window; connected components (or Jaccard of project-sets) = candidate cohorts. Accounts created within days of each other, hitting an overlapping project set, is a cluster.
3. **Cross-project duplicate density** — for a candidate cohort, mean pairwise similarity per §4.2.
4. **Newness concentration** — fraction of the cohort's accounts under N days old.

### 4.4 Campaign verdict — evidence-first, never a black box

```
campaign_score = Σ wᵢ · normalised_signalᵢ
  similarity_density, cohort_size, project_overlap, burstiness,
  account_newness, triviality_rate
```
Emit a signed `campaign_alert`:

```json
{
  "type": "campaign_alert",
  "detected_by": "proj-a",
  "window": {"start": "2026-10-31T21:00Z", "end": "2026-10-31T23:00Z"},
  "severity": "high",
  "cohort": {"accounts": 38, "median_account_age_days": 3, "projects_hit": 40},
  "evidence": {
    "mean_pairwise_similarity": 0.94,
    "similarity_tier": "minhash+embedding",
    "example_pairs": [{"a": "pr_0042", "b": "pr_0043", "jaccard": 0.97}],
    "burst": "38 PRs, 40 projects, 121 minutes",
    "triviality_rate": 0.97,
    "sample_prs": ["https://github.com/proj-a/pull/88", "…"]
  },
  "affected_projects": ["proj-a","proj-b", "…"],
  "explanation": "38 accounts created within 4 days issued near-identical PRs to 40 projects within 121 minutes…"
}
```
Every number in that alert comes from code; the LLM only writes `explanation` from those numbers with citations. **No verdict is ever model-produced.** Judges probe exactly this.

### 4.5 Fairness guardrails (do not skip — it's an explicit evaluation axis)

- Quarantine applies to **accounts linked to a confirmed campaign**, never to "unknown".
- Threshold on cohort evidence: a campaign needs ≥3 independent signals. One signal (e.g. account age) alone must never quarantine anyone — otherwise St. Hacktober 2020 repeats with you as the villain.
- **Newcomer green path**: unknown + non-trivial PR (linked issue, tests, real code) → routed to normal human review with a `newcomer` label and a neutral note. Unknown + trivial single-file docs PR → informational, still not blocked.
- **Bootstrap**: a newcomer's unknown status is escapable by (a) any trusted vouch, (b) a merged PR in good standing anywhere in the network, (c) completing a project's declared onboarding path.
- **Report your own false-quarantine rate.** A tool that says "I quarantined 0 of 12 legitimate newcomers" wins the fairness half of the rubric on the spot.

---

## 5. Repo layout & CLI

```
opentrust/
├── HACKATHON.md   LICENSE   README.md
├── pyproject.toml
├── .github/pull_request_template.md
├── .github/workflows/ci.yml
├── opentrust/
│   ├── crypto.py       # ed25519 sign/verify, canonical JSON, hash chain
│   ├── records.py      # dataclasses, JSON-schema validation, content hashing
│   ├── store.py        # append-only local log, ingest, dedupe by hash
│   ├── sync.py         # peer manifest, clone/pull, ingest, equivocation check
│   ├── graph.py        # trust digraph from trust_edge records
│   ├── eigentrust.py   # personalised power iteration (numpy)
│   ├── reputation.py   # subject scoring, verdicts, retractions, recency
│   ├── signals.py      # ContributionSignal extraction + derived features
│   ├── similarity.py   # MinHash/LSH tier 1 + embedding tier 2 (Ollama)
│   ├── campaign.py     # cohort clustering, burstiness, scoring, alert records
│   ├── policy.py       # thresholds, published policy record
│   ├── explain.py      # evidence bundles, markdown/incident report rendering
│   └── cli.py
├── network/            # simulated 20–50 project fixtures + incoming PRs + labels
├── tools/gen_network.py# scenario generator (campaign + legit newcomers)
├── examples/           # input snapshot → real output (JSON alert + report.md + graph.svg)
└── tests/
```

CLI:

```bash
opentrust keygen --project proj-a
opentrust vouch   --subject github:@new-dev --scope code_quality --reason "…" --evidence URL
opentrust denounce --subject github:@spam --reason "…" --evidence URL --severity high
opentrust trust   --project proj-b --weight 0.8
opentrust sync    --manifest network.json          # clone/pull peers, ingest, verify sigs
opentrust score   --subject github:@new-dev        # verdict + full contribution breakdown
opentrust scan-pr --pr incoming/pr_0042.json       # per-PR decision for one project
opentrust campaigns --window 2h --min-cohort 5     # campaign alerts
opentrust report  --format markdown|json|graphviz  # demo output
```

Exit codes: `0` clean, `1` campaign found (CI-usable), `2` error. `--no-llm` degrades Tier 2 + explanation to Tier 1 + templates; **never crashes without a model.**

---

## 6. Why AI-text detection alone is insufficient (rehearse this answer)

Your pitch must contain it, because it's an explicit key consideration:

1. **The label is wrong.** OP-slop is a coordination pattern: N accounts, one window, many projects, near-identical payloads. A single human writing one mediocre PR is indistinguishable — and harmless.
2. **AI-detection classifiers are unreliable.** High false-positive rates on non-native English writers, easy to evade by paraphrasing, no calibrated probability. Using them as a gate is both unfair and ineffective.
3. **Legitimate contributors use AI.** Ghostty's own AI policy permits AI-assisted contributions with disclosure. Punishing AI-authored *text* punishes your best newcomers — the exact failure the problem statement tells you to avoid.
4. **What you actually measure:** account age, cross-project velocity, payload similarity (shingle **and** semantic), cohort overlap, effort signals. Behaviour, not authorship.

That answer also converts your LLM usage from a liability into a design virtue: the model reads *reasons and evidence quality* and *catches paraphrased duplicates*, while **decisions stay deterministic and auditable.**

---

## 7. The AI model's real jobs (name these in HACKATHON.md)

| Job | Model | Why it's not decorative |
|---|---|---|
| Semantic duplicate detection (Tier 2) | `nomic-embed-text` (Ollama) | catches paraphrased campaign payloads shingles miss — a measurable recall gain you can report |
| Vouch/denounce **scope + evidence-quality** parsing | `qwen2.5:7b-instruct` or `llama3.1:8b` (Ollama) | turns free-text reasons into structured `scope[]` and an evidence-strength score that feeds corroboration requirements |
| Incident report narrative | same | writes the human-readable campaign report, quoting only numbers/citations produced by code |
| Newcomer context note | same | neutral "what this person actually did" summary for the maintainer |

Justification line for `HACKATHON.md`: *"qwen2.5:7b-instruct via Ollama — best local trade-off on short structured-extraction tasks at 4-bit; nomic-embed-text — small, fast, strong paraphrase retrieval, runs on CPU. No cloud APIs; verdicts are deterministic, models only produce features and explanations."*

---

## 8. Eval harness + your own simulator

You cannot develop against data you don't have. **Build the generator first** (`tools/gen_network.py`) — 15 minutes and it de-risks the whole night:

- N=40 projects, synthetic keys, random trust edges (a few trusted hubs, a couple of untrusted isolates — including one that denounces a legitimate newcomer)
- 12 legit newcomers: varied but plausible histories (some with 1 merged PR, some brand new, one with a vouch from a trusted project)
- 1 campaign: 38 accounts created within 4 days, near-identical PR text with per-repo word swaps, 120-minute burst, trivial docs diffs
- optional `labels.json` ground truth

Then report, on your own fixture and on anything organizers hand you:

```
Campaign PRs flagged:       38/38   (recall 100%)
Clean PRs flagged:           0/N    (false-positive rate)
Legitimate newcomers quarantined: 0/12
Reputation AUC (campaign vs legit): 0.97
Runtime on 40 projects / 500 PRs: 3.2s
```

Accept organizer input flexibly: `--network <dir> --incoming <dir> --labels <file>`. If their schema differs, add an adapter — it's 30 lines and it's the difference between scoring and not scoring on the flagship eval.

---

## 9. 12-hour schedule (from 8:30 PM)

| Time | Task | PR |
|---|---|---|
| 8:30–9:15 | skeleton, pyproject, CI green on empty pytest, CLI stub | #1 |
| 9:15–10:30 | `crypto` + `records` + `store` (sign, canonical JSON, hash chain, validate) | #2 |
| 10:30–11:30 | `graph` + `eigentrust` + tests (2-hop beats 1-hop-from-untrusted) | #3 |
| 11:30–12:30 | `reputation` — vouch/denounce/retract scoring, verdicts, policy | #4 |
| 12:30–1:15 | `tools/gen_network.py` — your simulated 40-project network | #5 |
| 1:15–2:15 | **`score` on @new-dev, exactly the slide's case, printed** | #4 cont. |
| 2:15–3:15 | `signals` + `similarity` Tier 1 (MinHash/LSH) | #6 |
| 3:15–4:15 | `campaign` — cohort clustering, burstiness, alert record | #7 |
| 4:15–5:00 | Tier 2 embeddings (Ollama) + `--no-llm` fallback + measure the recall delta | #8 |
| 5:00–5:30 | `report` markdown/JSON + graphviz graph, `examples/` captured | #9 |
| 5:30–6:00 | README, eval numbers table, **green CI on final commit**, demo rehearsal | – |
| 6:00–6:30 | **Freeze.** Screenshot the CI run | – |

Night-one gate: if `opentrust score` on the slide's example doesn't print correctly by 2 AM, stop adding features and fix that. It's the centrepiece of the demo.

---

## 10. The 8-minute pitch

1. **20 s** — "A campaign hit 40 projects in 2 hours. Every maintainer saw one PR. Nobody saw the campaign."
2. **2.5 min** — live: `opentrust score --subject @new-dev` → `trusted`, "vouched by Project B, which you trust (trust weight 0.71 via 2 hops)"; then show Project X's denounce sitting in the **ignored** bucket because you don't trust X. That's the slide, reproduced. Then `--project X` viewpoint → the same data, a different verdict. **Same network, different opinions — that's decentralization made visible.**
3. **2 min** — campaign: `opentrust campaigns --window 2h` → alert with 38 accounts / 40 projects / 121 minutes / 0.94 similarity, cohort graph on screen, evidence list with PR URLs.
4. **1.5 min** — fairness: `0 of 12 legit newcomers quarantined`, green path shown, newcomer bootstrap path explained.
5. **1 min** — how: Ed25519 signed append-only records in each project's git repo (no server, no DB), personalised EigenTrust for propagation, two-tier similarity, deterministic verdicts with local LLM features.
6. **30 s** — trade-offs: eventual consistency, no global consensus, equivocation detectable-by-gossip rather than prevented; precision-over-recall on quarantine; unknown ≠ untrusted.

Likely Q&A (any member can be asked — assign owners):
- "Why not a blockchain / why no server?" → git + signatures + no consensus requirement; the threat model doesn't include Byzantine majority, it includes *untrusted peers*, which asymmetric trust handles.
- "What if a big project goes rogue and denounces everyone?" → its weight is bounded by who trusts it; mass denouncements with no corroboration get down-weighted; retraction + appeal path; append-only means the record is public and judgeable.
- "How does a truly new contributor ever get in?" → unknown ≠ untrusted; green path; bootstrap rules; only campaign-linked accounts are quarantined.
- "Isn't this just PageRank?" → it's personalised EigenTrust seeded at *you*, over signed trust edges, with scoped claims and evidence-weighted negatives; explain the difference (asymmetry, teleport-to-self, per-viewpoint results).
- "What about your cold start with 20 projects?" → trust edges are sparse by design; α keeps scores conservative; unknowns stay unknown rather than defaulting to trusted or blocked.

---

## 11. Traps

- **Don't build a blockchain.** Say "signed append-only log + gossip," not "distributed ledger." No consensus mechanism is needed and adding one wastes three hours.
- **Don't use transitive closure with a depth cutoff.** It's the naive answer to their first key consideration and it's easy to spot.
- **Don't let denouncements from untrusted nodes count.** The slide tests exactly this; it's a free point if you build it structurally (weight-multiplied) rather than with an `if` branch.
- **Don't mix negative and positive signals into one graph.** Trust propagates; denouncements are evidence *conditioned on* trust.
- **Don't gate on AI-detection.** It's the stated anti-pattern and it fails the fairness axis.
- **Don't skip the newcomer eval.** Recall without a false-quarantine number reads as an unfinished project.
- **Never post to real repositories.** Run on `network/` fixtures only — that's an explicit data/security rule.
- **Don't let the verdict be a model output.** Deterministic decisions + LLM features is the story that survives Q&A.

---

## 12. Honest risk note

P7 has the **widest rubric** of the eight — organizers can't score it as mechanically as P5's "did you find the right sentence," so interpretation and demo quality carry more weight, in both directions. That's upside if your pitch is tight and your numbers exist; downside if you build a rich system and can't show two clean numbers. Build the generator and the numbers table early, and this is a top-3 project. Leave them to 5 AM and you'll have an impressive system you can't prove works.
