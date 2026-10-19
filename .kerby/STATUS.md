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
| **Phase** | Integration — evals complete and in review; more hiring tools next |
| **Milestone** | int-more-ats (M5b) |
| **Milestone Goal** | SmartRecruiters, Workday (verified company list) and opt-in USAJOBS, without crowding tech boards out of the cap |

---

## Next Up

| Priority | Task | Dependencies |
|----------|------|--------------|
| 1 | M5b C1–C2 — SmartRecruiters adapter, fixtures, seed import and seed check | evals merged |
| 2 | M5b C3–C4 — Workday adapter (keyword search) and a verified Workday company list | C1 |
| 3 | M5b C5–C9 — USAJOBS opt-in, keyword-source support and field-aware board selection, SKILL.md coverage text, nurse re-run, skill-evaluator | C3, C4 |

---

## Blockers

None.

---

## Notes for Human Review

- Seed check flagged six boards with more than 2,000 jobs as possible aggregators (ashby:bjakcareer, greenhouse:andurilindustries, greenhouse:spacex, lever:aogarciaagency, lever:boxlunch, lever:tsmg). SpaceX and Anduril are real employers; none were added to the denylist without verification.
- Ground truth 2026-10-19 is two-model consensus (Codex + Gemini), not human-labelled; a human re-label is a ROADMAP follow-up.
- Branch protection on `main` is a repo setting only the maintainer can turn on (the seed-check workflow token has write access).
