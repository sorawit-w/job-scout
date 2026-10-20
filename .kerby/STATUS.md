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
| **Phase** | claude.ai memory (notice once, paste block with saved, applied and dismissed roles) on main, not yet released; launch smoke tests still open |
| **Milestone** | none in progress; deploy-launch (M6) open until the smoke tests pass |
| **Milestone Goal** | pick the next milestone from the ROADMAP follow-ups |

---

## Next Up

| Priority | Task | Dependencies |
|----------|------|--------------|
| 1 | Maintainer: install smoke tests on Claude Code, Codex, npx and claude.ai (DEVELOPER_TODO) | latest release published |
| 2 | Maintainer: decide whether to cut a release for the Unreleased changes (claude.ai memory, seed-check auto-merge) | — |
| 3 | Choose the next milestone from the ROADMAP follow-ups | — |

---

## Blockers

- The install smoke tests are maintainer actions (DEVELOPER_TODO).

---

## Notes for Human Review

- Seed check flagged six boards with more than 2,000 jobs as possible aggregators (ashby:bjakcareer, greenhouse:andurilindustries, greenhouse:spacex, lever:aogarciaagency, lever:boxlunch, lever:tsmg). SpaceX and Anduril are real employers; none were added to the denylist without verification.
- Ground truth 2026-10-19 is two-model consensus (Codex + Gemini), not human-labelled; a human re-label is a ROADMAP follow-up.
- Branch protection on `main` is a repo setting only the maintainer can turn on (the seed-check workflow token has write access). The weekly seed check now merges routine updates itself; a rule that requires CI checks on `main` would block that merge, because a bot push starts no CI.
