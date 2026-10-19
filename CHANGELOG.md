# Changelog

All notable changes to `job-scout` are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versioning is semver.

## [0.2.0] — 2026-10-19

**HTML report (M7).** Every search can now be opened as one self-contained page.

### Added
- `scripts/report.py` writes `report.html` in the run folder: the brief, the coverage line, and
  a full-width master–detail table — one row per shown role (fixed rank, a tiered fit meter
  where only 7–8/8 fits are colored, short pay, open since, a "1 flag" note), with details that
  open inline or, on screens 1200px and wider, in a sticky side pane you move through with ↑/↓.
  Each detail leads with a "Check first" box (gates that did not pass, and flags), then quoted
  reasons and risks, score meters, the four gates, an "Open posting" button and "Copy reply to
  chat" buttons. Then saved/applied and closed roles on a rerun, and the close-but-excluded
  lines. "Top fit" and "No flags" quick filters, a text filter and column sorting narrow the
  rows; phones keep the table with fewer columns; the page reads fully with JavaScript off and
  prints as a document. Fit is the sum of the four scores. The "Signal refined" theme (neutral
  gray, one teal accent) has light and dark modes.
- The page loads nothing: inline CSS and JS under a Content-Security-Policy that allows only its
  own script, every value HTML-escaped, `http(s)` links only.
- SKILL.md runs the report after the chat results and before `seen record`, and opens it when a
  local browser exists. A pasted `save 3 (Company, Title)` line acts on the named role.
- probe.py, filter.py and fetch_jd.py save the numbers the report needs (`boards.json` counts,
  `filter.json`, and the live row or drop reason in `jds.json`).
- Evals E12 and E13; design tokens in `docs/report-design.md`.

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
