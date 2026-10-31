# opentrust

**A decentralized trust network for open source contributions.**
Hacktoberfest 2026 · Hack Day Sonipat · Problem 07.

A spam campaign can send 38 near-identical pull requests to 40 projects in two hours.
Every maintainer sees one plausible PR. Nobody sees the campaign. Meanwhile the honest
first-time contributor gets caught in whatever blunt rule you invent to stop it.

`opentrust` lets projects publish **signed, scoped vouch and denouncement records** in
their own git repositories, choose **which other projects they trust**, and then answers
two questions:

1. **Should I trust this contributor?** — `trusted` / `unknown` / `quarantined`, computed
   from *your* viewpoint. A denouncement from a project you do not trust carries no weight.
2. **Is this a coordinated campaign?** — network-level detection with an evidence bundle,
   because the pattern only exists across projects.

There is **no server, no database and no consensus mechanism.** Each project is
authoritative over its own hash-chained, append-only records. Distribution is `git pull`.

---

## Install

```bash
pip install -e ".[dev]"
pytest -q
```

Optional local AI (open-weight, runs on your machine — never a cloud API):

```bash
ollama pull qwen3:4b-instruct-2507-q4_K_M     # reason/evidence parsing, incident narrative
ollama pull qwen3-embedding:0.6b        # Tier-2 paraphrase similarity
```

`opentrust` works without either model. See [Model usage](#model-usage).

## Quick start

```bash
# 1. build the simulated network (40 projects, 320 records, 50 incoming PRs)
python tools/gen_network.py --out network

# 2. verify every signature in the network
opentrust sync --manifest network/manifest.json

# 3. the problem statement's own example
opentrust score --manifest network/manifest.json --subject "github:@new-dev" --viewer proj-a
#    -> TRUSTED: vouched by proj-b, which proj-a trusts
#    -> proj-x's denouncement: ignored, issuer trust 0.000 < 0.10

# 4. the same records, a different project's opinion
opentrust score --manifest network/manifest.json --subject "github:@new-dev" --viewer proj-x
#    -> QUARANTINED. No global truth, only per-viewpoint answers.

# 5. catch the campaign
opentrust campaigns --incoming network/incoming
#    -> 1 campaign: 30 accounts, 30 projects, 107 min, similarity 1.00, 5/6 signals

# 6. the numbers
python tools/evaluate.py --network network
```

## Commands

| Command | Purpose |
| --- | --- |
| `opentrust keygen --project ID --out DIR` | Create a project identity (Ed25519) |
| `opentrust vouch --project ID --out DIR --subject WHO --scope SCOPE --reason TEXT` | Publish a scoped vouch |
| `opentrust denounce --project ID --out DIR --subject WHO --reason TEXT --evidence URL...` | Publish a denouncement (evidence required) |
| `opentrust trust --project ID --out DIR --target PROJECT --weight 0.8` | Declare trust in another project |
| `opentrust models` | Show which open-weight model each module uses, and whether it is live locally |
| `opentrust analyse --reason TEXT [--kind vouch\|denounce] [--no-llm]` | Parse a free-text reason into structured scope + evidence strength (local model) |
| `opentrust sync --manifest FILE` | Load and signature-verify the whole network |
| `opentrust score --manifest FILE --subject WHO --viewer PROJECT [--json]` | Assess one contributor from one viewpoint |
| `opentrust campaigns --incoming DIR [--window 120] [--min-cohort 5] [--tier2] [--json]` | Detect coordinated campaigns |
| `opentrust report --manifest FILE --subject WHO --viewer PROJECT --out FILE` | Markdown report |
| `opentrust graph --manifest FILE --viewer PROJECT` | Trust graph as Graphviz DOT |

Exit codes: `0` nothing found, `1` campaign detected (so this can gate CI), `2` error.

## How it works

### 1. Signed append-only records

A project's identity is an Ed25519 keypair, not a forgeable org name. Every statement is
signed and links to the previous record by hash, so each project's history is
tamper-evident without anyone's permission. Six record types: `vouch`, `denounce`,
`retract`, `trust_edge`, `campaign_alert`, `policy`. Corrections are new `retract`
records — nothing is ever deleted, so every judgement stays auditable.

### 2. Trust propagates one hop by default (personalised EigenTrust)

The default policy follows **one hop**: you see your trusted peers' vouches, but not
their peers'. Raising `max_trust_hops` in a project's published policy lets trust travel
further, with each extra hop decaying (α = 0.15 teleports back to you).

```
t(0)   = e_seed                                   all trust starts on me
t(k+1) = (1-α)·Cᵀ·t(k) + α·e_seed                 α = 0.15, teleport home
```

A peer reached through several strong, well-trusted paths scores high; a peer hanging off
one dubious edge scores ~0. Because the seed is *you*, trust is asymmetric and
viewpoint-dependent by construction — which is exactly why `proj-a` and `proj-x`
disagree about the same contributor.

### 3. Negative signals are evidence, not edges

Denouncements never enter the trust graph. They are multiplied by the issuer's trust
weight from your viewpoint, so **a denouncement from a project you do not trust moves
nothing.** Corroboration across independent trusted issuers raises credibility; one
hostile project can never damage a contributor by more than its own weight.

### 4. Campaigns are a network-level pattern

Per-PR signals (account age, triviality, target files, linked issue) are cheap and
explainable. Similarity is two-tier: MinHash shingles for identical payloads, local
embeddings for paraphrased ones. Authors are clustered when their payloads are
near-identical *and* they target different projects; clusters are then scored on six
independent signals (similarity, cohort size, project overlap, burst, account newness,
triviality). At least three must fire before anything is reported.

### 5. Unknown is not a rejection

`unknown` is the default state for every first-time contributor and is never a
quarantine. Only accounts linked to a campaign with multiple corroborating signals are
quarantined. A newcomer escapes `unknown` through any trusted vouch, a merged PR in good
standing, or a project's declared onboarding path.

## Model usage

| Model | Runs on | Job | Why |
| --- | --- | --- | --- |
| `qwen3:4b-instruct-2507-q4_K_M` | Ollama, localhost | Parse free-text vouch/denounce reasons into structured scope labels and evidence strength; draft the incident narrative from code-computed numbers | Best local trade-off on short structured extraction at 4-bit |
| `qwen3-embedding:0.6b` | Ollama, localhost | Tier-2 semantic PR similarity, to catch paraphrased campaign payloads | Strong paraphrase retrieval at 137M params, CPU-friendly |

**No verdict is produced by a model.** Trust propagation, reputation scoring, campaign
scoring and quarantine decisions are deterministic algorithms over signed records.
Models produce features and explanations only. `--no-llm` (default when no model server
is reachable) degrades Tier 2 to Tier 1 and explanations to templates; it never crashes.

`opentrust analyse --reason "..."` demonstrates the model's job directly, and
`--no-llm` shows the deterministic fallback (which is what CI and the graders' machines
will use if no model server is reachable).

Why not AI-text detection? Because slop is a *coordination* pattern, not a textual one.
Detectors are unreliable, evadable by paraphrasing, and they punish legitimate
contributors who — under Ghostty's own policy — are allowed to use AI. We measure
behaviour: account age, cross-project velocity, payload similarity, cohort overlap.

## Evaluation

From `python tools/evaluate.py --network network` (see `examples/evaluation.txt`):

| Metric | Result |
| --- | --- |
| Identical-payload campaign PRs caught | **30 / 30 (100%)** |
| Paraphrased-payload PRs caught | 0 / 8 with Tier 1; Tier 2 required |
| Legitimate PRs falsely flagged | **0 / 12** |
| Legitimate newcomers quarantined | **0 / 12** |
| Bad actor (corroborated denouncements) | quarantined, score −4.08 |
| Vouched newcomer | trusted, score +0.15 |
| Runtime | 0.3 s for 50 PRs, 40 projects |

## How this answers Problem 07

Every line in this table can be checked by running the command or the test.

| What the problem asks | How OpenTrust does it | Check it |
| --- | --- | --- |
| Projects keep public vouch and denouncement records | One signed record per file in each project's `trust/records/`. Existing Vouch `VOUCHED.td` lists can be imported and exported | `opentrust sync`, `tests/test_crypto.py`, `tests/test_vouchfile.py` |
| Projects exchange trust information | Plain files distributed by git; each record is Ed25519-signed and verified on load, so a copy from anywhere can be checked | `opentrust sync` (320 records verified, 0 rejected) |
| A trusts B, B trusts C: how does A see C? | One hop by default. A project can allow more hops in its policy; each extra hop counts for less | `tests/test_eigentrust.py::test_one_hop_by_default_more_on_request` |
| Bad or inaccurate denouncements can't ruin someone | Denouncements from projects you don't trust carry no weight. One trusted denouncement with weak evidence is shown as an allegation, not a block. Blocking needs corroboration from a second independent project or checkable evidence | `tests/test_reputation.py`, `examples/score-new-dev-as-seen-by-proj-x.txt` |
| Detect coordinated campaigns across projects | Clusters near-duplicate PRs, then scores six behavioural signals (similarity, burst timing, account age, project spread, cohort size, trivial changes) | `opentrust campaigns`, `tests/test_end_to_end.py` |
| Honest newcomers aren't excluded | No history means `unknown`, never `quarantined`. Newcomers get normal review | `tests/test_end_to_end.py::test_legit_newcomers_are_not_quarantined` (0 / 12 quarantined) |
| Newcomers can build trust | One vouch from a project you trust is enough to reach `trusted` | `tests/test_reputation.py::test_vouch_from_trusted_project_makes_contributor_trusted` |
| No central authority | No server and no shared database. Every project computes its own view from the records it chooses to trust | `opentrust score --viewer proj-a` vs `--viewer proj-x` |
| Why AI-text detection alone isn't enough | We don't use it. Plenty of good contributors write with AI tools, and spam can be made to read as human. Behaviour across many projects is much harder to fake | `opentrust/campaign.py` |

## Repository layout

```
opentrust/
  crypto.py      Ed25519 signing, canonical JSON, content digests
  records.py     record types, builders, validation
  store.py       append-only log, project/network loading, verification
  graph.py       trust digraph from trust_edge records
  eigentrust.py  personalised EigenTrust power iteration
  reputation.py  vouch/denounce/retract scoring, verdicts
  policy.py      published thresholds
  llm.py         local model integration: reason parsing, narratives, fallback
  signals.py     per-PR behavioural features
  similarity.py  Tier-1 MinHash, Tier-2 local embeddings
  campaign.py    cohort clustering, burstiness, campaign scoring
  explain.py     human-readable rendering
  cli.py         command line interface
tools/
  gen_network.py simulated 40-project network with campaign + newcomers
  evaluate.py    recall / false-positive / fairness numbers
network/         generated fixture network (regenerate with tools/gen_network.py)
examples/        real captured outputs
tests/           unit + end-to-end tests
```

## Licence

MIT. See `LICENSE`.
