# Roadmap

Legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked (with reason). Order is priority. Detail per milestone lives in `implementation-plan.yaml`.

### Phase 1: v0 (M1–M6)

- [!] M6 — Launch 0.1.0: repo public and v0.1.0 released (2026-10-19); listed on the agent-skills shelf; open until the maintainer runs the four install smoke tests (DEVELOPER_TODO)

### Phase 2: v0.2

- [x] M7 — HTML report: self-contained report.html per run (Signal theme, sort/filter, copy-a-reply, score grid); released as v0.2.0
- [x] M8 — Work-style match: optional fixed-choice questions, quoted match / conflict / not-stated signals per role, display only; released as v0.3.0

### Phase 3: v0.4

- [x] M9 — Rerun memory: a `judged` status so screened-but-unshown roles stop coming back as new; one ranked rerun list with NEW / CHANGED / SAVED badges; cached judgments reused when the posting and the brief are unchanged; released as v0.4.0

## Follow-ups

- [ ] Lever EU host (`api.eu.lever.co`) — not needed in v0: every sampled seed slug answered on `api.lever.co`
- [ ] Location table gaps: cities missing from `normalize.py`'s table resolve to no country; "Lima, PE" reads PE as a Canadian province; "Porto Alegre" matches Porto (PT); "Stuttgart, DE" reads DE as Delaware
- [ ] Region-to-country matching in filter.py: only "Americas" maps to countries today, so a DE or GB user's "Remote - Europe" role is removed by remote scope instead of kept with a flag
- [ ] Workable adapter
- [ ] Read up to 60 job descriptions when more than ~30 candidates are strong (M5 scorecard: generic titles miss the 40-pick cut)
- [ ] Human re-label of the 2026-10-19 key (it is two-model consensus today)
- [ ] CSV export with the full 11-column table
- [ ] Sector tagging beyond the 49 eval boards (today `industries_prefer` matches company names as a stand-in)
- [ ] Job connectors (Indeed / Dice / ZipRecruiter) as an employer-discovery source only, resolved to employer links — worth doing once Workday ships (M5b), so most employers a connector finds have a board job-scout can read
- [ ] More hiring tools after M5b: iCIMS, Taleo and Phenom first (Sacramento's large hospital systems use them), then SuccessFactors, TalentBrew, JazzHR, Recruitee
- [ ] Location-aware board order: boards near the user's home base before far ones (Workday locations often name a building, not a city or state)
- [ ] Workday jobs carry no remote/onsite field: a "Remote … California Residents Only" role reads as onsite
- [ ] Workday rows with no place or mode spend live-check reads (21 of 40 in the nurse run, none shown): read their detail records outside the 40-description budget, or cap them
- [ ] claude.ai Team/Enterprise egress test
- [x] Report: axe `heading-order` on a role's "Check first" heading once its detail opens inline at ~1024px (found in the M9 audit; on main since M7)
- [x] Root README "Status" section still describes the first release

## Shipped

- [x] M5b — More hiring tools: SmartRecruiters, Workday (verified company list), opt-in USAJOBS; board order by the brief's field; nurse live run 19/19 open (2026-10-19)
- [x] M5 — Evals: E1–E11, consensus ground truth (Codex + Gemini), scorecard vs jobscope (top 15: 13/33 vs 2/33), filter fixes from the fix loop (2026-10-19)
- [x] M4 — State and reruns: seen/diff, closed detection, rerun view, add-a-company (2026-10-19)
- [x] M3 — Matching: hard filters, title prefilter, live check, cite check, rubric, output format, relocation (2026-10-19)
- [x] M2 — Confirmation gate: profile schema, DOCX text, SKILL.md phases 0–3, trigger fixtures, gate evals (2026-10-19)
- [x] M1b — Data layer: net, normalize, Greenhouse/Ashby/Lever adapters, cache, probe, seed import + weekly seed check (2026-10-19)
- [x] M1a — Setup: agent-context, glossary, roadmap, plan, adapter contract, manifests, compat check, CI (2026-10-18)
- [x] M0 — Egress spike, connector and jobscope scorecards, competitor scan (2026-10-18, `docs/m0/`)
