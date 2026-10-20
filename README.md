# job-scout

An agent skill that finds open jobs that fit your resume. It reads employer job boards directly,
after you confirm a short search brief, and returns about 15 roles. Each role is checked open
today, links straight to the employer, and explains its fit with quotes from the job description.

- **Works in:** Claude Code, Codex, claude.ai (Pro/Max), and any agent that reads `SKILL.md`.
- **Reads:** Greenhouse, Ashby, Lever, SmartRecruiters and Workday boards, plus USAJOBS with
  your own free key.
- **Status:** Current release: `0.5.0`. See [Status](#status).

job-scout is not affiliated with any job board or employer.

## Why

Ask a chat assistant for jobs and you usually get links to job aggregators, roles that closed
weeks ago, and fit reasons the model made up. The job-board connectors we tested gave **0 direct
employer links** (`docs/m0/M0_REPORT.md`). The nearest open-source skill showed 4 of 18 strong
fits by default.

job-scout goes to the source instead: the public job-board APIs that employers post to. In a test
on 49 company boards with a senior frontend engineer's resume, **13 of job-scout's 15 shown roles
were strong fits**, against 2 of 15 for that skill. The answer key was labelled by two models, not
by people. Every shown role was open on a live check and linked to the employer
(`skills/job-scout/evals/results/2026-10-19-scorecard.md`).

## What it does

- Reads your resume (text, PDF, Markdown, HTML, `.docx`) or a description of what you do.
- Drafts a search brief and shows it to you before anything is searched. It asks about work
  mode, pay and visa sponsorship instead of guessing them.
- Checks up to 400 employer boards (600 at most) from a list of about 14,000 verified boards,
  plus any companies you add.
- Narrows the jobs with your brief, then reads up to 40 job descriptions and checks that each
  role is still open.
- Shows about 15 roles in one table, each with a direct employer link, quoted fit reasons, and
  honest unknowns ("pay not listed", "sponsorship not stated").
- Writes the same results as one HTML report you can open, sort, filter and print. It has a score
  breakdown per role and buttons that copy a reply ("save 3") to paste back into the chat.
- Optionally shows how each role fits the way you like to work (meetings, on-call, travel,
  autonomy, company stage): matches, doesn't match, or not stated, always with a quote from the
  posting. It never changes the ranking.
- Remembers what you saved, applied to or dismissed, and what it already judged, so the next run
  shows one ranked list with new and changed roles marked, without reading the same postings again.

## What it doesn't do

- It never applies, messages anyone, or writes cover letters.
- It never reads LinkedIn or any site behind a login.
- It never falls back to web search when a board can't be reached.
- It never pads the list with weak matches. If nothing fits, it says why.
- It never guesses protected traits (age, gender, race, religion, disability, and so on).

## When to use it

- "Here's my CV, what should I apply to?"
- "Find me remote frontend roles in the US."
- "Anything new since last week?"
- "Also check Linear and Figma for openings."

## When not to use it

- Cover letters or outreach messages: use a writing skill such as ghostwriter.
- Interview prep, resume rewrites, or salary negotiation.
- Recruiting: job-scout searches for job seekers, not for candidates.

## How it works

1. **Brief.** The skill reads your resume and fills a brief: target titles, level, places, work
   mode, pay floor, sponsorship. Each value is labelled with where it came from (your resume,
   your words, a default). You confirm it, or say "just go" to accept the labelled defaults.
2. **Network check.** One small request per job board. If the boards can't be reached, it stops
   and tells you which setting to change.
3. **Probe.** `probe.py` reads the boards most likely to fit your field, merges duplicate
   postings, and writes the jobs to a local run folder.
4. **Filter.** `filter.py` applies the brief: work mode, commute cities, remote country,
   level, titles, pay floor. It reports how many jobs each rule removed.
5. **Live check.** `fetch_jd.py` re-reads up to 40 roles on the employer's board. A closed role is
   dropped, and a role that changed since the search is checked against the brief again.
6. **Judge and cite.** The agent scores each role with a fixed rubric and quotes the job
   description for every reason. `cite_check.py` rejects any quote that is not in the text.
7. **Report.** `report.py` writes a self-contained `report.html` in the run folder. It loads
   nothing from the network and works with JavaScript off. The agent opens it when your setup has
   a browser.
8. **Remember.** Your feedback is stored locally, and the next run shows new and changed roles
   first.

The scripts use only the Python 3.9+ standard library: nothing to install.

## Design choices

- **Employer boards, not aggregators.** Every link goes to the company's own board. That is
  slower to build, but it is the only way to promise "open today".
- **A confirmed brief before any search.** A wrong guess about remote work or sponsorship
  wastes the whole run, so the skill asks first.
- **Quotes or it didn't happen.** A fit reason must quote the job description. A script checks
  every quote, so made-up reasons fail the run.
- **Board order by field.** Tech briefs check Greenhouse, Ashby and Lever first. Other fields
  check Workday and SmartRecruiters first, where hospitals and large employers post.
- **Search words are the only part of your brief that is sent.** Workday and USAJOBS are searched
  with your target job titles. Nothing else from your resume or brief leaves your machine.
  (USAJOBS also needs your key and email, sent as request headers only to USAJOBS.)

## Install

**Claude Code** (plugin marketplace):

```bash
/plugin marketplace add sorawit-w/job-scout
/plugin install job-scout@job-scout
```

**Codex:** add the marketplace from your shell, then install from inside Codex:

```bash
codex plugin marketplace add sorawit-w/job-scout
```

In Codex, run `/plugins`, pick the job-scout marketplace, install job-scout, and start a new
session. Codex blocks network access by default, so start it with network access on:

```bash
codex --sandbox workspace-write -c sandbox_workspace_write.network_access=true
```

**Any agent that reads `SKILL.md`** (Cursor, opencode, Claude Code and others), via
[`npx skills`](https://github.com/vercel-labs/skills):

```bash
npx skills add sorawit-w/job-scout
```

**claude.ai** (Pro or Max): download `job-scout-<version>.zip` from the
[Releases](https://github.com/sorawit-w/job-scout/releases) page, then upload it under
Settings → Capabilities → Skills. Code execution must be on, and its domain allowlist must allow
the job boards ("All domains" works). On Team or Enterprise plans an admin may need to add the
hosts listed in [PRIVACY.md](PRIVACY.md). Files don't persist between claude.ai conversations;
see [Where job-scout remembers](#where-job-scout-remembers).

**Updating:** the company list is refreshed every week. In Claude Code, run
`/plugin marketplace update job-scout` to refresh the catalog, then update the installed copy
from your shell with `claude plugin update job-scout@job-scout`; it loads in your next session,
or after `/reload-plugins`. Or turn on auto-update for the job-scout marketplace under
`/plugin` → Marketplaces. In Codex, run `codex plugin marketplace upgrade job-scout`. On
claude.ai, upload the newest zip from the Releases page.

**Optional, US federal jobs:** request a free key at
<https://developer.usajobs.gov/apirequest/>, then set `JOB_SCOUT_USAJOBS_KEY` and
`JOB_SCOUT_USAJOBS_EMAIL` in your environment. Never paste the key into a chat.

## Where job-scout remembers

| Where you run it | What it remembers between chats |
|---|---|
| Claude Code, Codex | Everything, in `~/.job-scout/`: your brief, the roles you have seen, saved, applied to or dismissed, and the newest 3 runs. |
| claude.ai | Nothing persists between chats. At the end of a run the skill gives you a block with your brief and your saved, applied and dismissed roles that are still open. Paste it into your next chat to pick up where you left off. Roles you only saw are not in it, so they can show as new again. |

## Coverage limits

job-scout is best for **tech and startup roles**. Coverage is partial elsewhere:

- Many hospitals and large employers use hiring tools job-scout can't read yet: iCIMS, Taleo,
  Phenom, SuccessFactors and others. In a live test for a nurse in Sacramento, the area's large
  hospital systems were all on those tools. job-scout found 19 open local roles, all from home
  health and staffing employers.
- Workday boards are searched by title, so a Workday role with an unusual title can be missed.
- One run checks at most 600 boards.

You can add any company that uses a supported tool: say "also check <company>", or give its
Workday careers URL. If a field is thin, the skill says so instead of filling the list.

## Privacy

Your resume, brief and history stay on your machine in `~/.job-scout/`. The only requests that
leave are job-board list and job requests. For Workday and USAJOBS, those requests carry your
target job titles; USAJOBS requests also carry your key and email as headers, because its API
requires them. There is no telemetry. Details: [PRIVACY.md](PRIVACY.md).

## Cross-skill

| Skill | How it fits |
|---|---|
| [ghostwriter](https://github.com/sorawit-w/agent-skills/tree/main/skills/ghostwriter) (if installed) | Drafts the outreach or recruiter message after job-scout finds the role. |

## Status

Current release, `0.5.0`: claude.ai memory and fresher data. On claude.ai the skill says once that
the chat can't keep history and hands you a block that restores your brief and your saved,
applied and dismissed roles in the next chat. Installed copies in Claude Code and Codex now pick
up the weekly company list. Earlier releases added the HTML report (`0.2.0`), work-style match
(`0.3.0`) and rerun memory (`0.4.0`); see
[CHANGELOG.md](CHANGELOG.md). Milestones M1–M9 in [`ROADMAP.md`](ROADMAP.md) are done, except
the launch milestone's install smoke tests. Planned next: more hiring tools (iCIMS, Taleo,
Phenom), job connectors as a way to discover employers, and board order by distance from home.
Spec: [`docs/HANDOFF.md`](docs/HANDOFF.md).

## Contributing

The easiest way to help is to add a company: one row in `skills/job-scout/data/companies.csv`.
See [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

The board list builds on [corpHuntingMCP](https://github.com/ZmoleCristian/corpHuntingMCP) (0BSD)
and [ats-scrapers](https://github.com/kalil0321/ats-scrapers) (MIT).
[jobscope](https://github.com/canmenzo/jobscope) (MIT) was a reference; no code was copied.
See [NOTICE](NOTICE).

## License

MIT — see [`LICENSE`](LICENSE).
