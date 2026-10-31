# HACKATHON.md

Hacktoberfest 2026 · Hack Day Sonipat · 31 Oct – 1 Nov 2026

## Team

**Team name:** ZeroDay

**Members**

- Anurag Kumar
- Abhigya Sachdeva
- Lakshya Agrawal

## Problem statement

**Problem 07: Decentralized Trust Network for Open Source Contributions**

## What we're building

We're calling it **OpenTrust**.

Each project keeps its own signed list of the people it vouches for and the people it has denounced. Each project also decides which other projects' lists it pays attention to. There's no central reputation database. On top of that, projects share a small summary of incoming PRs (an embedding, timing, account age), so a spam campaign that hits 40 repos in two hours shows up as one campaign instead of 40 separate problems that each maintainer deals with alone.

We started from Ghostty's [Vouch](https://github.com/mitchellh/vouch). It already gets the basics right: a plain-text `VOUCHED.td` file, maintainers vouch for or denounce people, and the project decides what follows from that. The part this problem asks about, and the part Vouch leaves open, is what happens *between* projects. If A trusts B and B denounces someone, should A care? How much? And what if B got it wrong?

Here's how we plan to answer those questions in the first version:

- **Lists are signed.** Every project has an Ed25519 key and signs its trust file. Anyone can check that a record really came from that project and wasn't changed along the way. We're not using a blockchain. Signed files are enough for this, and they're much easier to run.
- **Trust doesn't spread on its own.** A project picks the peers it trusts. By default we follow one hop: if A trusts B, A sees B's vouches, but A doesn't automatically trust everyone B trusts. A project can allow more hops in its policy, and each extra hop counts for less.
- **One denouncement is an allegation, not a verdict.** A single denouncement with no linked evidence is shown to maintainers but doesn't block anyone. Before we recommend blocking someone, we need evidence, or denouncements from more than one independent project you trust. Records can be disputed, and they expire.
- **Unknown doesn't mean suspicious.** A newcomer with no history goes through normal review. They only get flagged if their PR actually turns up inside a detected campaign.
- **Campaigns are detected from behaviour, not writing style.** We look at signals together: near-duplicate PRs (identical or reworded), tight timing across repos, very new accounts, and the same kind of low-value change repeated. We don't try to guess whether text was written by AI. Lots of good contributors use AI tools, and spammers can make text look human with no effort, so that check doesn't tell you much.

Every decision OpenTrust makes comes with the reasons and the evidence behind it, so a maintainer can look at it and disagree.

## Models we use

We use two open-weight models. Both are Apache-2.0 and both run locally through [Ollama](https://ollama.com). The product doesn't call any closed or paid AI API, not even as a fallback.

| Model | Runs via | What it does in OpenTrust |
|---|---|---|
| `qwen3:4b-instruct-2507-q4_K_M` (Qwen3-4B-Instruct-2507) | Ollama | Reads a PR (title, description, diff) and returns structured JSON: what kind of change it is, whether it changes anything real, and short notes. It also writes the plain-English summary of a detected campaign from the evidence we've already computed. |
| `qwen3-embedding:0.6b` (Qwen3-Embedding 0.6B) | Ollama | Turns each PR into a vector so we can find PRs across different repos that say the same thing in different words. |

### Why Qwen3-4B-Instruct-2507

Our main dev machine is a MacBook Pro M3 with 8 GB of memory, and that decided a lot. macOS, a browser and our dev servers already take about half of it, so both models together have to stay around 3–4 GB.

- The job is narrow: read a diff and fill in a fixed JSON schema. A 4B model is plenty for that.
- The 4-bit build is 2.5 GB. Together with the embedding model it's about 3.2 GB, which leaves room for everything else on an 8 GB laptop.
- We use the instruct version on purpose. Plain `qwen3:4b` on Ollama is the thinking variant, which writes out its reasoning before answering. That makes it slower, and we don't need it for classification.
- It follows instructions well for its size (83.4 on IFEval according to the model card) and has a long context, so big diffs won't break anything. We still trim diffs, and we cap the context we actually load to keep memory down.
- It's Apache-2.0.

We looked at Gemma 4 first, since the organizers recommend it. On Ollama, even the smallest E2B build is a 4.6 GB+ download because it includes vision and audio. We don't need either, and it wouldn't fit next to everything else on 8 GB. Bigger machines could run it fine. It just isn't the right fit for ours.

Using the same model family for both jobs also means one runtime and one set of quirks to learn.

### Why Qwen3-Embedding 0.6B

- With AI tools, rewording the same spam PR 40 times takes no effort. Exact hashing misses that. Embeddings catch it.
- It's built for retrieval, including code, accepts up to 32K tokens, and takes an instruction. That lets us tell it to focus on what a change does instead of how it's worded.
- At 639 MB it's small enough to pull in CI, so our tests can use the real model instead of a mock.
- It's Apache-2.0.

### What the models don't do

The models don't make trust decisions. Trust scores, policy checks, signature verification and graph clustering are all plain deterministic code that gives the same answer every run. The models only supply inputs (a classification, a similarity score) and a written summary.

If a model returns something we can't trust, like JSON that doesn't match the schema or a summary that mentions a PR that isn't in the cluster, we throw it away instead of showing it. If Ollama isn't running, OpenTrust still works. It just runs without the semantic signals and says so in its output.

### If this changes

We wrote this file before writing any code. If we swap a model, we'll update this file in a PR and explain why. We'll name the AI coding assistants we use while building in each PR, as the rules ask.

## Links

- Vouch: https://github.com/mitchellh/vouch
- Ghostty PR that introduced it: https://github.com/ghostty-org/ghostty/pull/10559
- Qwen3-4B-Instruct-2507 model card: https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507
- Qwen3-Embedding 0.6B model card: https://huggingface.co/Qwen/Qwen3-Embedding-0.6B