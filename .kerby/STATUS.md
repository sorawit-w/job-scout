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
| **Phase** | Implementation — matching complete and in review; state and reruns next |
| **Milestone** | impl-state-reruns (M4) |
| **Milestone Goal** | seen/diff memory, rerun view of new and changed roles, feedback recording, adding companies, SKILL.md phases 8–9 |

---

## Next Up

| Priority | Task | Dependencies |
|----------|------|--------------|
| 1 | M4 R1–R2 — `state.py` seen/diff (an errored or unprobed board never marks jobs closed) and the diff/record/mark CLI | matching merged |
| 2 | M4 R3–R5 — `filter.py` state tags and only-new reruns; `companies.py` add; probe always includes the user's companies | R1 |
| 3 | M4 R6–R8 — SKILL.md feedback and rerun phases, day2 replay world, E5/E6, skill-evaluator pass | R1–R5 |

---

## Blockers

None.

---

## Notes for Human Review

- Seed check flagged six boards with more than 2,000 jobs as possible aggregators (ashby:bjakcareer, greenhouse:andurilindustries, greenhouse:spacex, lever:aogarciaagency, lever:boxlunch, lever:tsmg). SpaceX and Anduril are real employers; none were added to the denylist without verification.
- Ground truth: 12 of the 18 M0 roles are hybrid or in-office outside LA, per their own descriptions; they count only for a persona open to relocation (the ground-truth file now says so). The full re-label stays the human V4 task in M5.
- Branch protection on `main` is a repo setting only the maintainer can turn on (the seed-check workflow token has write access).
