# Project Status

> **Position only.** This file answers *where do things stand* — never *what
> happened*, *which version*, or *what a PR is doing*. Provenance has authorities
> already: versions live in the manifests, commits and branches in git, history in
> `.kerby/memory.log`, ticket state in the tracker. A copy here can only drift from
> them, so do not restate one. Rewrite this file from what those sources currently
> say — never from memory of what you set an hour ago.

---

## Current Position

| Field | Value |
|-------|-------|
| **Phase** | Integration — state and reruns complete and in review; evals next |
| **Milestone** | int-evals (M5) |
| **Milestone Goal** | E1–E9 run end to end, re-labelled ground truth, recall ≥15/18, a scorecard against jobscope |

---

## Next Up

| Priority | Task | Dependencies |
|----------|------|--------------|
| 1 | M5 V1–V2 — personas and E1–E9 with assertions | state and reruns merged |
| 2 | M5 V3–V4 — re-labelling snapshot + sheet; the human labels the ground truth (maintainer task) | V1 |
| 3 | M5 V5–V10 — scorer for jobscope runs, scorecard, benchmark, fix loop, trigger eval, final skill-evaluator | V4 |

---

## Blockers

None.

---

## Notes for Human Review

- Seed check flagged six boards with more than 2,000 jobs as possible aggregators (ashby:bjakcareer, greenhouse:andurilindustries, greenhouse:spacex, lever:aogarciaagency, lever:boxlunch, lever:tsmg). SpaceX and Anduril are real employers; none were added to the denylist without verification.
- Ground truth: 12 of the 18 M0 roles are hybrid or in-office outside LA, per their own descriptions; they count only for a persona open to relocation (the ground-truth file now says so). The full re-label stays the human V4 task in M5.
- Branch protection on `main` is a repo setting only the maintainer can turn on (the seed-check workflow token has write access).
