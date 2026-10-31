# Set this once in your clone and every commit prompts you for the required fields.
#   git config commit.template .gitmessage

## Guidelines reminder

Every commit message and every pull request must name:

1. the **AI coding agent** that helped write it (Copilot, Cursor, Claude Code, ChatGPT, or `none`)
2. the **open-weight models the product uses** (`qwen3:4b-instruct-2507-q4_K_M`, `qwen3-embedding:0.6b`, or `none in this change`)

Example:

```
Add campaign cohort clustering

Coding agent: Claude Code
Models used in project: qwen3:4b-instruct-2507-q4_K_M, qwen3-embedding:0.6b
```

## Workflow

- `main` is PR-only after the first commit. No direct pushes.
- Every change: branch → PR → CI green → merge.
- Fill in every section of `.github/pull_request_template.md`.
- Merge early and often. A PR that is open at 6:30 AM does not exist for scoring.

## Local checks before pushing

```bash
pytest -q
python tools/gen_network.py --out network   # fixtures are regenerable, not precious
```

## Do not commit

- `*.key`, `.env`, `.env.*` — the fixture keys under `network/*/private.key` are
  synthetic and gitignored; real secrets must never enter the tree.
