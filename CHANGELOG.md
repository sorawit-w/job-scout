# Changelog

All notable changes to `job-scout` are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versioning is semver.

## [0.4.0] — 2026-10-19

**Rerun memory (M9).** A rerun shows one ranked list with new and changed roles marked, and reuses
what it already judged instead of reading the same postings again.

### Changed
- A rerun now shows **one ranked list**: roles shown before, roles screened before but never
  shown, saved roles and new or changed ones, in the rubric's order. Badges mark what moved and
  never change the order: **NEW** (never shown before), **CHANGED** (shown before, and the posting
  changed: before → after), **SAVED**. A role shown before and unchanged has no badge and says
  "First shown <date>". Applied and dismissed roles stay out of the table (`--all` brings them
  back); applied roles keep their "still open" list.
- The rerun coverage line reads "Checked N of M company job boards: K new or changed since last
  time · showing top R of J matches." With nothing new, the full list still shows, under one line:
  "No new or changed postings since last time."
- The report has the same order and badges, a "New only" filter, and "first shown" and "what
  changed" in each role's details.

### Added
- Cached judgments are reused. filter.py marks a role `cached` when seen.json holds a judgment for
  this posting and brief; the read budget (up to 40 descriptions) skips those and goes to new and
  changed roles first. `fetch_jd.py --check-only` live-checks the cached roles without printing
  their descriptions, and `state.py judged carry` writes their judgments into the run's
  results.json. Every carried quote is checked again against this run's description; a carried
  role that fails is judged again from scratch.
- `state.py judged rank` puts results.json in the rubric's order (total, then exact remote scope,
  then newest) and decides which roles are shown (no failed gate, fit 5 or more, within the result
  count).

### Fixed
- `seen record` used to remember only the roles it showed, so every role an earlier run read and
  cut (by a gate, by score or by the result count), or never read at all, came back as new on the
  next run. It now remembers them too, under a new status, `judged`: screened, never shown. On a
  rerun, filter.py keeps them as candidates with state `judged`, not `new`.
- `seen diff` no longer reports `new`: it counted every listed role, even ones the brief rules
  out. The per-candidate `state` from filter.py is the count of new roles.

### Added
- Each read role keeps its judgment (gates, scores, total, quoted reasons and risks) in seen.json,
  with the posting it judged and a fingerprint of the brief fields the rubric reads. The cached
  judgment is valid only while both are unchanged: editing the brief invalidates every one.
  Changing your work style keeps the gates and scores, because work style never affects fit, but
  drops the cached work-style signals so they are written again for your new choices. A cached
  judgment also needs the same job description: an employer can edit a posting in place.
- `state.py judged forget` drops every cached judgment and keeps every status. A new resume can
  change the skills score, and the profile does not store the resume.
- A judged role becomes `seen` the first time it is shown. `seen mark` cannot set `judged`.
- Judged roles not listed on any board for 60 days are dropped from seen.json. No other status
  is ever dropped.

### Compatibility
- A seen.json written by this version cannot be read by v0.3.0 or earlier, which rejects the
  `judged` status. Keep using the newer version once you have run it.

## [0.3.0] — 2026-10-19

**Work-style match (M8).** Each role now shows what its posting says about how you like to work.

### Added
- An optional question after you confirm the brief: meetings (async-first or meetings OK),
  on-call, travel, autonomy, and company stage, each with fixed choices and each skippable. It is
  asked once and saved as `work_style` in the profile; "change my work style" edits it. Existing
  users are offered it once on their next search.
- Per role, every topic you set shows **matches**, **doesn't match** or **not stated**, with a
  quote from the job description that `cite_check.py` verifies. The posting is the only evidence:
  a company's fame or size never counts.
- Conflicts appear in the chat notes and in the report's "Check first" box; the report's role
  detail lists every signal in a new "Work style" section, and the brief shows your choices.
- The signals never change fit, rank, or which roles are shown. To hide roles, use a dealbreaker.
- The profile keeps only the fixed choices, never a reason given for one. Evals E14 and E15.
- Each run keeps a copy of the brief it was searched with (`<run>/profile.json`), so a later
  "change my work style" never relabels an older run's report. `cite_check.py` checks every shown
  role covers each saved topic exactly once, and that a choice that allows something ("travel OK")
  is never reported as a conflict.

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

### Changed
- A saved or applied role whose live check finds the posting gone now counts as closed, even
  while the board list still shows it and on partially searched boards (Workday, USAJOBS).
  `seen record`, `seen diff` and the report agree on it. A grouped role stays open while any of
  its postings is still listed, and then links to a live one.

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
