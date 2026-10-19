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
| **Phase** | Setup — repo scaffold |
| **Milestone** | setup-repo (M1a) |
| **Milestone Goal** | Scaffold a stdlib-Python skill repo with a green gate locally and in CI on Python 3.9 and 3.13 |

---

## Next Up

| Priority | Task | Dependencies |
|----------|------|--------------|
| 1 | M1b D1 — `net.py`: UA, timeout, retry, request budget, health check, record/replay | M1a merged |
| 2 | M1b D3/D4 — location parsing, remote scope, variant collapse (test-first) | M1a merged |
| 3 | M1b D2 — record HTTP fixtures; verify pay fields per ATS | D1 |

---

## Blockers

None.

---

## Notes for Human Review

- GitHub settings the weekly seed check will need before M1b's last task are listed in `DEVELOPER_TODO.md`.
