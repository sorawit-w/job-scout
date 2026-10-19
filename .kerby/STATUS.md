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
| **Phase** | v0.3 — work-style match in review; launch smoke tests still open |
| **Milestone** | v03-work-style (M8); deploy-launch (M6) open until the smoke tests pass |
| **Milestone Goal** | optional fixed-choice work style; quoted match / conflict / not-stated signals per role; display only |

---

## Next Up

| Priority | Task | Dependencies |
|----------|------|--------------|
| 1 | M8 PR — Codex review findings fixed, squash-merged | skill-evaluator recorded (E4, E14, E15, N8, N9: 24/24) |
| 2 | Publishing the work-style release (maintainer's call after merge) | M8 merged |
| 3 | Maintainer: install smoke tests on Claude Code, Codex, npx and claude.ai (DEVELOPER_TODO) | release published |

---

## Blockers

- The install smoke tests are maintainer actions (DEVELOPER_TODO).

---

## Notes for Human Review

- Seed check flagged six boards with more than 2,000 jobs as possible aggregators (ashby:bjakcareer, greenhouse:andurilindustries, greenhouse:spacex, lever:aogarciaagency, lever:boxlunch, lever:tsmg). SpaceX and Anduril are real employers; none were added to the denylist without verification.
- Ground truth 2026-10-19 is two-model consensus (Codex + Gemini), not human-labelled; a human re-label is a ROADMAP follow-up.
- Branch protection on `main` is a repo setting only the maintainer can turn on (the seed-check workflow token has write access).
