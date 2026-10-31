# Submission checklist — tonight, in order

Print this or keep it open. It is the only page that matters for compliance.

## ⏰ Deadlines

| Time | Action | Who |
| --- | --- | --- |
| **8:30 PM** | First commit (`HACKATHON.md`) on `main` | 1 person |
| **8:30 PM** | **MLH check-in, every member**, code **`6DMN96`** | all 3 |
| **8:30 PM** | Repo link submitted on MLH (team leader only) | 1 person |
| **11:00 PM** | **Team created on Cadence** — strict, must match MLH team | 1 person |
| 12:00 AM | Mentors stop (Krishna, Neetanshu, Kushagar, Sai) | — |
| **6:30 AM** | **Final push.** Repos frozen. CI must be green on that commit | all |
| 8:30 AM | Presentations, 8 min pitch + 4 min Q&A, 8 panels | all |

## 1. Wi-Fi

`RU_Guest` · user `dev.club` · password `dc`

## 2. First commit (before 8:30 PM)

```bash
cd /home/user
git init -b main
# edit HACKATHON.md FIRST: team name, all 3 names, problem 07, both models + why
git add HACKATHON.md
git commit -m "docs: team, problem statement and AI models

Coding agent: <yours>
Models used in project: qwen3:4b-instruct-2507-q4_K_M, qwen3-embedding:0.6b"
# create the public GitHub repo (empty), then:
git remote add origin git@github.com:<you>/opentrust.git
git push -u origin main
```

- [ ] Repo is **public**
- [ ] Licence is **MIT** (`LICENSE` is already in place)
- [ ] `HACKATHON.md` contains: problem statement, team name, every member, every model + why
- [ ] Nothing else in that first commit

## 3. Every member: MLH check-in (8:30 PM)

1. Open <https://www.mlh.com/events/hacktoberfest-hack-day-sonipat-x-rishihood-university>
2. Sign in to MLH
3. Check-in code: **`6DMN96`**
4. **Each of the three of you must do this individually.**

- [ ] A checked in
- [ ] B checked in
- [ ] C checked in

## 4. Team leader: submit the project on MLH (8:30 PM)

1. Same MLH event page → **Challenges** → **Add Submission**
2. Repo link, project name, description, tech used
3. Challenge: **Best Open-Source AI Project** (all teams)
4. **Submit Project**
5. **Your Submission → Add Member** → add both teammates

- [ ] Submitted
- [ ] Both members added

> You can keep pushing to the repo until 6:30 AM. Submission time is not a freeze —
> but nothing after 8:30 PM is submitted for you, so don't miss it.

## 5. Cadence team (before 11:00 PM)

1. <https://cadence.devclubxnst.com/login> → **Forgot password** → set a new password
2. No email? Check spam, then ask any volunteer to add you, then reset again
3. Create the team: **1–4 members**, matches your MLH team exactly
4. **No team switching.** Once set, it stays.

- [ ] Team created on Cadence by 11:00 PM
- [ ] Matches the MLH team name and members

## 6. Repo compliance (checked by the automated grader)

- [ ] First commit is `HACKATHON.md` only, on `main`
- [ ] Branch protection-ish discipline: everything after that is a PR (no direct pushes)
- [ ] `.github/pull_request_template.md` present and filled in on every PR
- [ ] `.github/workflows/ci.yml` installs the project and runs the tests
- [ ] **CI green on the final commit** ← hard requirement; red CI loses correctness points
- [ ] `tests/` contains real tests (43 currently)
- [ ] `examples/` contains sample input + **real** output the tool produced
- [ ] `README.md` has install + run instructions that work from a clean clone
- [ ] No secrets: no `*.key`, no `.env`, no tokens in history
      (`git log -p --all | grep -iE 'api[_-]?key|secret|token'` should be clean)
- [ ] Models named in `HACKATHON.md` are **actually used by the code**
      (`qwen3:4b-instruct-2507-q4_K_M` → `opentrust/llm.py`; `qwen3-embedding:0.6b` → `opentrust/similarity.py`)
- [ ] Every commit message names the coding agent + models (`.gitmessage` template)

## 7. Six minutes before 6:30 AM

```bash
pytest -q                                   # local green
python tools/evaluate.py --network network  # numbers are current
git status                                  # nothing uncommitted and forgotten
git push                                    # final push
```

- [ ] Screenshot the green GitHub Actions run on the final commit
- [ ] Confirm the repo is public and opens in a logged-out tab
- [ ] Re-read `BUILD-PLAN-P7-TEAM3.md` §4 (demo) and §5 (Q&A ownership) before sleeping
