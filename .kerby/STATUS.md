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
| **Phase** | Deployment — launch docs and release zip in review |
| **Milestone** | deploy-launch (M6) |
| **Milestone Goal** | First public release: docs, release zip, install smoke tests; going public is the maintainer's call |

---

## Next Up

| Priority | Task | Dependencies |
|----------|------|--------------|
| 1 | M6 PR — review findings fixed, squash-merged | skill-evaluator clean |
| 2 | Maintainer: make the repo public, publish the release zip, run the four install smoke tests (DEVELOPER_TODO) | M6 merged |
| 3 | Follow-ups in ROADMAP (iCIMS, Taleo, Phenom first) | release published |

---

## Blockers

- Going public, the GitHub release and the install smoke tests are maintainer actions (DEVELOPER_TODO).

---

## Notes for Human Review

- Seed check flagged six boards with more than 2,000 jobs as possible aggregators (ashby:bjakcareer, greenhouse:andurilindustries, greenhouse:spacex, lever:aogarciaagency, lever:boxlunch, lever:tsmg). SpaceX and Anduril are real employers; none were added to the denylist without verification.
- Ground truth 2026-10-19 is two-model consensus (Codex + Gemini), not human-labelled; a human re-label is a ROADMAP follow-up.
- Branch protection on `main` is a repo setting only the maintainer can turn on (the seed-check workflow token has write access).
