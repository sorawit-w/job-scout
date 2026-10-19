# Changelog

All notable changes to `job-scout` are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versioning is semver.

## [0.1.0] — 2026-10-19

**First release.** job-scout finds open roles that fit a resume, from employer job boards.

### Added
- **Confirmation gate (M2):** the skill shows a search brief with the source of every value and
  asks about work mode, pay and sponsorship before any search; "just go" uses labelled defaults
  that filter nothing out. The profile has no field for protected traits and rejects unknown
  fields.
- **Job boards (M1b, M5b):** Greenhouse, Ashby, Lever, SmartRecruiters and Workday adapters,
  plus opt-in USAJOBS with the user's own key. About 14,000 verified boards in
  `data/companies.csv`, checked weekly by a GitHub Action that opens a PR.
- **Matching (M3):** `filter.py` applies the brief and reports what each rule removed;
  `fetch_jd.py` live-checks up to 40 roles; a fixed rubric scores fit; `cite_check.py` rejects
  any quote that is not in the job description.
- **Memory and reruns (M4):** saved, applied and dismissed roles; reruns lead with new and
  changed roles; a board that failed never marks a role closed. `companies.py` adds companies.
- **Evals (M5):** 11 evals with assertions, a two-model ground-truth key, and a scorecard: 13 of
  15 shown roles were strong fits on the 49-board test, against 2 of 15 for jobscope.
- **Launch (M6):** README, PRIVACY, CONTRIBUTING; `scripts/build_release.py` builds the release
  zip with claude.ai-safe frontmatter; CI live-checks companies a PR adds.

### Notes
- Best for tech and startup roles. Hospitals and large employers on iCIMS, Taleo, Phenom or
  SuccessFactors are not readable yet (see `ROADMAP.md`).

## [0.0.1] — 2026-10-18

**Repo scaffold (M1a).** No runtime behavior yet — this release only sets up the project.

### Added
- `agent-context.yaml`, `CONTEXT.md` (domain glossary), `ROADMAP.md`, and `implementation-plan.yaml` covering M1a–M6.
- The ATS adapter port (`skills/job-scout/scripts/adapters/__init__.py`) with its contract test.
- Plugin manifests for Claude Code and Codex, `skills/job-scout/VERSION`, and `scripts/check-skill-compat.py` (copied from kerby; checks SKILL.md frontmatter and version parity). It also fails when a manifest declares a skill with no `SKILL.md`, or a `SKILL.md` exists that no manifest declares — so the manifests declare no skill until M2 adds it.
- CI on Python 3.9 and 3.13: compile, compat check, unit tests.

### Notes
- The spec is `docs/HANDOFF.md` (rev. 3); M0 results are in `docs/m0/`.
