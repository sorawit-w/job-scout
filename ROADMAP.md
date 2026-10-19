# Roadmap

Legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked (with reason). Order is priority. Detail per milestone lives in `implementation-plan.yaml`.

### Phase 1: v0 (M1–M6)

- [~] M5 — Evals: E1–E9, re-labelled ground truth, recall ≥15/18, beat jobscope's top-15
- [ ] M5b — More hiring tools: SmartRecruiters, Workday (with a verified company list), opt-in USAJOBS
- [ ] M6 — Launch 0.1.0: README, PRIVACY, CONTRIBUTING, NOTICE, release zip, install smoke tests (going public is the maintainer's call)

## Follow-ups

- [ ] Lever EU host (`api.eu.lever.co`) — not needed in v0: every sampled seed slug answered on `api.lever.co`
- [ ] Location table gaps: cities missing from `normalize.py`'s table resolve to no country; "Lima, PE" reads PE as a Canadian province; "Porto Alegre" matches Porto (PT); "Stuttgart, DE" reads DE as Delaware
- [ ] Region-to-country matching in filter.py: only "Americas" maps to countries today, so a DE or GB user's "Remote - Europe" role is removed by remote scope instead of kept with a flag
- [ ] Workable adapter
- [ ] CSV export with the full 11-column table
- [ ] Sector tagging beyond the 49 eval boards
- [ ] Job connectors (Indeed / Dice / ZipRecruiter) as an employer-discovery source only, resolved to employer links — worth doing once Workday ships (M5b), so most employers a connector finds have a board job-scout can read
- [ ] More hiring tools after M5b: SuccessFactors, TalentBrew, JazzHR, Recruitee, iCIMS, Taleo
- [ ] claude.ai Team/Enterprise egress test

## Shipped

- [x] M4 — State and reruns: seen/diff, closed detection, rerun view, add-a-company (2026-10-19)
- [x] M3 — Matching: hard filters, title prefilter, live check, cite check, rubric, output format, relocation (2026-10-19)
- [x] M2 — Confirmation gate: profile schema, DOCX text, SKILL.md phases 0–3, trigger fixtures, gate evals (2026-10-19)
- [x] M1b — Data layer: net, normalize, Greenhouse/Ashby/Lever adapters, cache, probe, seed import + weekly seed check (2026-10-19)
- [x] M1a — Setup: agent-context, glossary, roadmap, plan, adapter contract, manifests, compat check, CI (2026-10-18)
- [x] M0 — Egress spike, connector and jobscope scorecards, competitor scan (2026-10-18, `docs/m0/`)
