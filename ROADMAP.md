# Roadmap

Legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked (with reason). Order is priority. Detail per milestone lives in `implementation-plan.yaml`.

### Phase 1: v0 (M1–M6)

- [~] M1a — Setup: agent-context, glossary, roadmap, plan, adapter contract, manifests, compat check, CI
- [ ] M1b — Data layer: net, normalize, Greenhouse/Ashby/Lever adapters, cache, probe, seed import + weekly seed check
- [ ] M2 — Confirmation gate: profile schema, DOCX text, SKILL.md phases 0–3, trigger fixtures, gate evals
- [ ] M3 — Matching: hard filters, title prefilter, JD fetch + live check, cite check, rubric, output format
- [ ] M4 — State and reruns: seen/diff, closed detection, add-a-company slug guessing
- [ ] M5 — Evals: E1–E9, re-labelled ground truth, recall ≥15/18, beat jobscope's top-15
- [ ] M6 — Launch 0.1.0: README, PRIVACY, CONTRIBUTING, NOTICE, release zip, install smoke tests (going public is the maintainer's call)

## Follow-ups

- [ ] SmartRecruiters adapter — field check done 2026-10-19 (works; paged lists, one request per description); corpHuntingMCP also lists SmartRecruiters tenants, so it is the first coverage expansion
- [ ] Lever EU host (`api.eu.lever.co`) — not needed in v0: every sampled seed slug answered on `api.lever.co`
- [ ] Location table gaps: cities missing from `normalize.py`'s table resolve to no country; "Lima, PE" reads PE as a Canadian province; "Porto Alegre" matches Porto (PT)
- [ ] Workable adapter
- [ ] Workday adapter (v0.1; jobscope's MIT adapter as reference)
- [ ] CSV export with the full 11-column table
- [ ] Sector tagging beyond the 49 eval boards
- [ ] Job connectors (Indeed / Dice / ZipRecruiter) as an employer-discovery source only, resolved to employer links
- [ ] claude.ai Team/Enterprise egress test

## Shipped

- [x] M0 — Egress spike, connector and jobscope scorecards, competitor scan (2026-10-18, `docs/m0/`)
