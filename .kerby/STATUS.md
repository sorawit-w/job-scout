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
| **Phase** | Foundation — data layer complete; implementation next |
| **Milestone** | impl-confirmation-gate (M2) |
| **Milestone Goal** | Profile schema, DOCX text, SKILL.md phases 0–3 (route check, ingest, brief + confirmation gate, health check), trigger fixtures, gate evals |

---

## Next Up

| Priority | Task | Dependencies |
|----------|------|--------------|
| 1 | M2 G1 — profile validate/save/show in `state.py` (unknown keys rejected) | data layer merged |
| 2 | M2 G3 — SKILL.md frontmatter + phases 0–3; re-add manifest skill declarations | G1 |
| 3 | M2 G5/G6 — trigger fixtures and gate evals E1/E4/E7/E9 | G3 |

---

## Blockers

None.

---

## Notes for Human Review

- Seed check flagged six boards with more than 2,000 jobs as possible aggregators (ashby:bjakcareer, greenhouse:andurilindustries, greenhouse:spacex, lever:aogarciaagency, lever:boxlunch, lever:tsmg). SpaceX and Anduril are real employers; none were added to the denylist without verification.
- Branch protection on `main` is a repo setting only the maintainer can turn on (the seed-check workflow token has write access).
