# job-scout

Finds open jobs that fit your resume by reading employer job boards directly, after you confirm
a short search brief. Returns about 15 roles, each checked open today, linked straight to the
employer, and explained with quotes from the job description.

---

## Why this exists

Chat answers about jobs tend to link to aggregators, include roles that closed weeks ago, and
give fit reasons nobody can check. job-scout reads the public job-board APIs that employers post
to (Greenhouse, Ashby, Lever, SmartRecruiters, Workday, and USAJOBS with your own key), so
every link is the employer's own page and every reason quotes the posting.

## What it does

- Reads your resume (text, PDF, Markdown, HTML, `.docx`) or a description of what you do.
- Shows a search brief before any search, with the source of each value, and asks about work
  mode, pay and sponsorship instead of guessing.
- Checks up to 400 boards from about 14,000 verified ones, plus companies you add.
- Live-checks up to 40 roles and shows about 15, with quoted fit reasons and labelled unknowns.
- Writes the results as one self-contained HTML report (sort, filter, print, copy-a-reply buttons).
- Remembers saved, applied and dismissed roles, so reruns show what is new.

## What it doesn't do

- No applying, no messages, no cover letters.
- No LinkedIn and no sites behind a login.
- No web-search fallback, and no padding with weak matches.
- No guesses about protected traits.

## When to use it

- "Here's my CV, what should I apply to?"
- "Find me remote frontend roles in the US."
- "Anything new since last week?"
- "Also check Linear and Figma."

## When not to use it

- Cover letters or outreach (ghostwriter, if installed), interview prep, resume edits, salary
  advice, or recruiting.

## How it works

Brief → network check → probe the boards (`scripts/probe.py`) → filter by the brief
(`scripts/filter.py`) → live check and descriptions (`scripts/fetch_jd.py`) → score with the
rubric and quote the description (`scripts/cite_check.py` rejects any quote not in the text) →
write the HTML report (`scripts/report.py`) → remember feedback (`scripts/state.py`). Standard-library Python 3.9+, nothing to install.

## Privacy — where your data lives

Your resume, brief and history stay in `~/.job-scout/` (or `JOB_SCOUT_HOME`). Only job-board
requests leave your machine. Workday and USAJOBS searches carry your target job titles and
nothing else from your brief. No telemetry.

## Design choices worth knowing

- **The brief comes first.** Nothing is searched until you confirm it or say "just go".
- **Board order follows your field.** Tech briefs check Greenhouse, Ashby and Lever first; other
  fields check Workday and SmartRecruiters first.
- **Unknowns are shown, not hidden.** "pay not listed" and "work mode not stated" are labels on
  the row.

## Install

- **Claude Code:** `/plugin marketplace add sorawit-w/job-scout`, then
  `/plugin install job-scout@job-scout`.
- **Codex:** `codex plugin marketplace add sorawit-w/job-scout` in your shell, then `/plugins` in
  Codex to install it, then a new session. Codex needs network access on.
- **Any agent:** `npx skills add sorawit-w/job-scout`.
- **claude.ai:** upload the release zip under Settings → Capabilities → Skills, with code
  execution on and the job-board hosts allowed.
- **USAJOBS (optional):** set `JOB_SCOUT_USAJOBS_KEY` and `JOB_SCOUT_USAJOBS_EMAIL`. Get a free
  key at <https://developer.usajobs.gov/apirequest/>.

## Cross-skill integration

| Skill | Relationship |
|---|---|
| [ghostwriter](https://github.com/sorawit-w/agent-skills/tree/main/skills/ghostwriter) (if installed) | Drafts outreach or recruiter messages; job-scout hands those requests to it. |

## Status and scope

Best for tech and startup roles. Coverage is partial for hospitals and large employers that use
iCIMS, Taleo, Phenom or SuccessFactors, which job-scout can't read yet. US-focused location
handling.

## License

MIT. Entry point: [`SKILL.md`](SKILL.md). Board field notes:
[`references/ats-notes.md`](references/ats-notes.md).
