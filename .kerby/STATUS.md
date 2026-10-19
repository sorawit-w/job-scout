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
| **Phase** | Implementation — confirmation gate complete; matching next |
| **Milestone** | impl-matching (M3) |
| **Milestone Goal** | Hard filters, title prefilter, JD fetch with live check, cite check, rubric, output format, SKILL.md phases 4–8 |

---

## Next Up

| Priority | Task | Dependencies |
|----------|------|--------------|
| 1 | M3 X1–X3 — `filter.py` hard filters, title prefilter, display variant + pay gate | confirmation gate merged |
| 2 | M3 X4–X5 — `fetch_jd.py` (live check, trim) and `cite_check.py` | X1 |
| 3 | M3 X6–X8 — rubric, output format, SKILL.md phases 4–8 | X4, X5 |

---

## Blockers

None.

---

## Notes for Human Review

- Seed check flagged six boards with more than 2,000 jobs as possible aggregators (ashby:bjakcareer, greenhouse:andurilindustries, greenhouse:spacex, lever:aogarciaagency, lever:boxlunch, lever:tsmg). SpaceX and Anduril are real employers; none were added to the denylist without verification.
- Branch protection on `main` is a repo setting only the maintainer can turn on (the seed-check workflow token has write access).
