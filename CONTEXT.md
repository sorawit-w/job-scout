# Project Context

> Domain glossary and shared language for this project. Read this at session start. Use these terms in code, commit messages, and prose so humans and agents speak the same language.

## How to use this file

- **Read at session start.** The agent reads `CONTEXT.md` as part of project detection.
- **Use the terms.** When a concept here has a name, use that name — not a description.
- **Propose additions, don't silently edit.** When new domain jargon emerges, surface it before writing.
- **Enduring vocabulary, not session state.** Session state lives in `.kerby/STATUS.md`; decisions and lessons in `.kerby/knowledge/`; this file is the glossary.

## Glossary

### Board
One employer's public job list on one ATS (applicant tracking system), named `ats:slug` — e.g. `greenhouse:vercel`, `ashby:harvey`. The unit the probe fetches and the cache stores. Lives in `skills/job-scout/data/companies.csv`.

### Job key
The stable id of one posting: `ats:slug:job_id`. Used in `seen.json`, run files, and `results.json`.

### Posting vs role
A **posting** is one job id on a board. A **role** is what the user sees: one row that may collapse several postings (see *Regional variant*). Recall is scored against postings; output is shown as roles.

### Search brief
The table of search parameters (target roles, seniority, work mode, pay floor, sponsorship, …) the skill drafts from the resume, each with a `Source` (`resume`, `inferred`, `default`, `you`, `needs you`). Saved as `profile.json` once confirmed.

### Confirmation gate
The rule that no request reaches any job board until the user has confirmed or edited the search brief (or explicitly said "just go", in which case defaults are shown, labelled). HANDOFF §4.

### Live check
Evidence, from this run or a cache entry younger than the TTL, that a posting is still open on the employer's board. No role is shown as open without one.

### Unverified board
A board that answers `200` with zero jobs — a wrong slug or a company that moved ATS. Never counted as coverage. Distinct from a **dead** board (`404`/`410`).

### Regional variant
The same role posted several times for different regions (e.g. Ashby's "Design Engineer - Americas / Canada / EU / UK"). Collapsed into one role that keeps every posting in `variants[]`.

### Remote scope
Where a remote role may be worked from, as a list (`["US"]`, `["US","CA"]`, `["AMER"]`, `["ANY"]`) or `null` when the posting does not say. Never guessed.

### Near miss
A role removed by a filter but close enough to show in the short "close but excluded" list, with the one reason it was removed — so the user can spot an over-tight filter.

### Judged role
A role an earlier run screened but never showed: read and cut (by a gate, by score or by the result count), or a candidate never read. Its `seen.json` status is `judged`, set only by `seen record`; it becomes `seen` the first time it is shown. A read one keeps its cached judgment, which is reused only while the posting and the brief are unchanged.

## Module map

- `skills/job-scout/` — the installable skill (SKILL.md, references, scripts, data, evals)
- `skills/job-scout/scripts/adapters/` — one module per ATS behind a shared contract (the port)
- `scripts/` — maintainer and CI tools, not shipped (seed import/check, compat check, scoring, release)
- `tests/` — offline unit tests on recorded HTTP fixtures
- `docs/` — the handoff spec, M0 results, and pre-M0 reference material

## Superseded terms

<!-- When a term is retired, mark it here with the replacement. Don't delete. -->
