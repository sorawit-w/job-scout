---
name: job-scout
description: >-
  Finds open jobs that fit the user's resume by reading employer job boards directly
  (Greenhouse, Ashby, Lever), after the user confirms a short search brief. Returns about
  15 roles checked open today, each linked straight to the employer, with fit reasons quoted
  from the job description and honest unknowns ("pay not listed"). Remembers seen, saved,
  applied and dismissed roles so reruns show what's new. Best for tech and startup roles.
  Triggers when the user wants to find or match jobs: "find me jobs", "match my resume to
  roles", "what should I apply to", "here's my CV, what's out there", "any new roles since
  last time", "check Linear and Figma for openings". Does NOT trigger for: cover letters or
  outreach messages (ghostwriter, if installed), interview prep, resume rewriting, salary
  negotiation, or recruiter-side sourcing.
instructions: |
  Load this skill when: the user wants open roles that fit their resume or background, wants
  to know what to apply to, or wants to re-check for new roles since a previous search.
  Do NOT load this skill when: the user wants a cover letter, an outreach or recruiter message
  drafted, interview preparation, resume edits, offer or salary advice, or to source candidates.
tags: [job-search, resume, careers, greenhouse, ashby, lever]
metadata:
  tier: draft
---

# job-scout

Turn a resume into a short list of roles that are **open today**, linked **straight to the
employer**, with fit reasons **quoted from each job description**. You never search the job
boards until the user has seen and confirmed what you are about to search for.

Scripts live in `scripts/` inside this skill's folder (the folder holding this SKILL.md).
Run them with `python3`; they use only the standard library. State lives in `~/.job-scout/`
(or `$JOB_SCOUT_HOME`), never in the user's project.

## What this skill is NOT

- **Not a writer.** No cover letters, outreach or recruiter messages. Hand outreach to
  `ghostwriter` if installed; for cover letters, say drafting is out of scope for job-scout.
- **Not an applicant.** It never applies, emails, or messages anyone. The user applies.
- **Not a scraper.** No LinkedIn, no sites behind a login, no aggregators. It reads the public
  job-board APIs employers publish (Greenhouse, Ashby, Lever) and nothing else.
- **Not a guesser.** It never invents pay, sponsorship, remote status, or that a role is open.
  Unknowns stay visible: "pay not listed", "sponsorship not stated".

## Phase 0 — Route check (before anything else)

Decide whether this is a job search. If the request is any of these, do not run a search:

| Request | Do this |
|---|---|
| Cover letter for a role | Say cover letters are out of scope for job-scout. Offer to find more roles instead. |
| Outreach / recruiter / follow-up message | Hand off to `ghostwriter` if installed, with the job URL. Otherwise say drafting is out of scope. |
| Interview prep, resume rewrite, salary or offer advice | Say job-scout only finds roles; answer normally without running any script. |
| Find, match, or re-check roles | Continue to Phase 1. |

Why: these neighbours share words like "role" and "resume", and running a search when the
user wanted a letter wastes their time and the job boards' goodwill.

## Phase 1 — Ingest the resume

Accept whatever the user gives:

- **Pasted text, Markdown, HTML, PDF** — read it directly. (In Codex, if you cannot read a PDF,
  run `pdftotext resume.pdf -` if it exists; otherwise ask the user to paste the text.)
- **.docx** — run `python3 scripts/docx_text.py resume.docx` and read its output.
- **No resume at all** ("I'm a marketing manager in Austin, what's out there?") — work from
  what they said. The gate below still runs; more fields will be `needs you`.

Extract a draft profile: target roles (2–5 job titles they would actually apply for), useful
title synonyms, seniority (e.g. Senior / Staff / Lead) and track (individual contributor vs
manager), home base (city), current employer, and core skills.

**Never infer protected attributes** — age, race, gender, religion, nationality, disability,
family status — not from names, photos, dates, schools or anything else, and never ask about
them. The profile has no field for them, and `state.py` rejects any it is given. If the user
volunteers one ("I'm 52", "I'm originally from Nigeria"), leave it out silently: do not repeat
it, comment on it, or record it. Visa status is different — the user may state it, and it is
used only as the sponsorship filter.

If `python3 scripts/state.py profile show` returns a saved profile, start from it: this is a
rerun. Show the brief with what changed since last time ("same as last time — change
anything?") instead of re-deriving everything.

## Phase 2 — Search brief and confirmation gate (required)

**Rule: no request reaches any job board until the user confirms or edits the brief.** The one
exception is an explicit "just go" / "skip the questions" / "use your best guess" — and even
then you show the brief, with every assumed value labelled `default`, and proceed in the same
reply.

Why: wrong parameters waste the request budget and anchor the ranking on the wrong things, and
people trust results more when they have seen the assumptions behind them.

**"Just go" never means guessing the three ask-only fields.** For work mode, pay floor and
sponsorship, use the defaults that filter nothing out — all work modes (remote limited to the
home-base country, `open_to_relocation: true` so hybrid or onsite roles elsewhere in that country
stay in, flagged), `base_pay_floor: null`, `needs_sponsorship: "undisclosed"` — label each
`default`, and list those three as optional follow-ups after the brief ("these three answers
would sharpen the results"). A wrong guess here silently hides roles; a non-filtering default
only costs some extra results.

### Show one compact table

```
Search brief — confirm or edit before I search

| Parameter         | Value                                               | Source             |
|-------------------|-----------------------------------------------------|--------------------|
| Target roles      | Design Engineer · Staff Frontend · Design Systems   | resume             |
| Seniority / track | Senior, Staff · individual contributor              | resume             |
| Home base         | Pasadena, CA                                        | resume             |
| Work mode         | ?                                                   | needs you          |
| Base pay floor    | ?                                                   | needs you          |
| Visa sponsorship  | ?                                                   | needs you          |
| Exclude companies | current employer (Acme)                             | inferred — confirm |
| Industries        | AI / developer tools preferred                      | inferred           |
| Recency           | all open roles; flag ones open over 90 days         | default            |
| Results           | 15                                                  | default            |
```

`Source` is one of: `resume`, `inferred`, `default`, `you` (the user already said it in this
conversation), or **`needs you`**. Anything the user stated earlier in the conversation
("remote only, US") is `you` — do not ask it again.

### What you may and may not fill in

| Field | Rule |
|---|---|
| Target roles, seniority, track, home base | From the resume; the user confirms. |
| Title exclusions (e.g. mechanical, RF, "Product Designer" for an engineer) | Infer; show only if non-obvious. |
| **Work mode** (remote / hybrid / onsite) | **Never guess. Ask.** |
| **Remote scope** | Ask if they chose remote — many remote roles are limited to one country. |
| **Relocation** | Ask if they chose hybrid or onsite: would they move for the right role? Never infer it from past moves. If yes, roles elsewhere in their home or remote-scope countries stay in, flagged "relocation". |
| **Visa sponsorship** | **Never guess or infer.** Ask plainly: yes / no / prefer not to say. Used only as a filter. |
| **Base pay floor** | **Never guess. Ask** (a number, or "no floor"). Roles with no listed pay are kept and labelled "pay not listed" unless the user says hide them. |
| Industries | Infer softly; label `inferred`. |
| Current employer | Infer from the resume; ask to confirm excluding it. |
| Must-haves / dealbreakers | Ask once, optionally. |

### Ask once, briefly

- Ask only what is missing or critical: **at most about 5 questions, in one message.** Number
  them and offer the choices inline (e.g. "1. Work mode: remote (US) / LA-area hybrid / onsite —
  pick any; for hybrid or onsite, would you relocate?").
- Use a structured choice tool if your environment has one (e.g. an ask-the-user tool);
  otherwise plain text.
- Write for anyone, not just engineers: no "ATS", "slug", "JSON", or "API" in questions or
  results. Say "job boards", "companies", "search".

### Be honest about coverage before searching

job-scout reads Greenhouse, Ashby and Lever boards — mostly tech and startup employers. If the
target roles are mostly outside that world (nursing, retail, trades, teaching, government,
large non-tech enterprises), say so **in the brief**: "Most employers in your field don't use
the job boards I can read, so results will be thin." Offer to search anyway; never pad the
results with weak matches to compensate.

### Save the confirmed brief

Write the confirmed profile as JSON and save it:

```
python3 scripts/state.py profile save --stdin <<'JSON'
{"schema": 1, "target_roles": [...], "title_synonyms": [...], "title_exclusions": [...],
 "seniority": [...], "track": "ic", "home_base": "...", "work_modes": ["remote", "hybrid"],
 "commute_cities": ["Los Angeles", "Pasadena", ...], "remote_scope": ["US"],
 "open_to_relocation": false, "needs_sponsorship": "no",
 "base_pay_floor": {"amount": 180000, "currency": "USD", "interval": "year"},
 "hide_no_pay": false, "industries_prefer": [...], "industries_exclude": [], "companies_include": [],
 "companies_exclude": ["Acme"], "must_haves": [], "dealbreakers": [], "recency_flag_days": 90,
 "result_count": 15, "sources": {"target_roles": "resume", "work_modes": "you", ...}}
JSON
```

- `needs_sponsorship` is `yes`, `no`, or `undisclosed`; `base_pay_floor` is `null` for "no floor".
- `commute_cities`: if they accept hybrid or onsite, list the cities within a reasonable commute
  of their home base and include them in the brief so they can correct it.
- If `save` prints `errors`, fix the JSON and save again — never drop the user's answer to make
  it pass. Unknown fields are rejected on purpose.
- **claude.ai:** files do not persist between conversations. After saving, tell the user once
  and offer the profile as a code block they can paste next time.

## Phase 3 — Check the network

Run `python3 scripts/probe.py --health`.

- `{"ok": true, ...}` → continue.
- `"ok": false` → **stop.** Say plainly that this environment can't reach the job boards, name
  which ones (`hosts`), and say which setting allows it:
  - **Codex:** run with network access, e.g.
    `codex --sandbox workspace-write -c sandbox_workspace_write.network_access=true`
    (or set the same in `~/.codex/config.toml`).
  - **claude.ai:** Settings → Capabilities → Code execution → domain allowlist. "All domains"
    works; a Team or Enterprise admin may need to add `boards-api.greenhouse.io`,
    `api.ashbyhq.com` and `api.lever.co`.
  - **`hint: "tls"`:** a corporate proxy is intercepting HTTPS; the user's IT setup must trust it.

  **Do not fall back to web search.** A web-search list is exactly what job-scout exists to
  replace: aggregator links, closed roles, wrong dates.

## Phase 4 — Probe the job boards

Run `python3 scripts/probe.py`. It picks up to 400 company boards (the user's named companies
first), fetches them politely with a cache, merges regional duplicates, and prints one JSON
summary: `run` (the run id), `boards.probed` / `boards.available`, `jobs`, `collapsed`.
The run's files live in `~/.job-scout/runs/<run>/` (or `$JOB_SCOUT_HOME/runs/<run>/`).

- Exit 3 → the network is blocked: give the Phase 3 stop message.
- Exit 4 → the request cap was hit: continue with the partial results and say so.

## Phase 5 — Narrow, then read the job descriptions

1. Run `python3 scripts/filter.py`. It applies the confirmed brief deterministically (work mode,
   location, remote scope, level, track, excluded companies and titles, pay floor) and prints
   `counts`, ranked `candidates` (each `strong` or `borderline`, with `flags`) and up to 5
   `near_misses`. With **zero candidates**, stop and explain using `counts.removed` (see
   `references/output-format.md` §4) — never pad.
2. Choose **up to 40** candidates whose descriptions are worth reading: all plausible `strong`
   ones, then `borderline` titles that could be the target role in substance (a title like
   "Software Engineer, Product" may be exactly a design-engineering job). Skip ones the title
   already rules out.
3. Run `python3 scripts/fetch_jd.py --keys <key1>,<key2>,...`. It re-checks each job on the
   employer's board (the live check) and returns `jobs` (open, with a trimmed `jd`), `closed`,
   and `unverified`. **Show only `open` jobs**; never present a closed or unverified job as open.

## Phase 6 — Judge fit, with quotes

Read `references/rubric.md` and follow it: three pass/fail gates (location, sponsorship, pay),
four 0–2 scores, a quote from the job description for every claim. Write the result to
`<run dir>/results.json`, then run:

```
python3 scripts/cite_check.py < <run dir>/results.json
```

If it reports `failed` claims, re-read the description and fix or delete each one, then run it
again until `"ok": true`. Why: a confident claim the description doesn't support is exactly the
failure job-scout exists to prevent.

## Phase 7 — Show the results

Follow `references/output-format.md`: one coverage line, the six-column table (employer links
only), one notes line per row with the quoted why/risk and "open since", 3–5 "close but
excluded" lines, then the feedback prompt.

## Phase 8 — Feedback

Ask what to do with the roles ("save 1", "applied 3", "dismiss 2: too senior"). Remembering
them across runs arrives in the next milestone; until then, say the feedback can't be saved yet.
If feedback implies a brief change ("I keep dismissing hybrid roles"), propose the change and
confirm it — never change the brief silently.

## Phase 9 — Reruns (not built yet)

Showing only what's new since last time arrives in the next milestone. For now a rerun is a
fresh search from the saved brief (Phase 1 already starts from it).

## Cross-skill integration

| Skill | Relationship |
|---|---|
| [`ghostwriter`](https://github.com/sorawit-w/agent-skills) *(if installed)* | Drafts outreach and recruiter messages for a role job-scout found. Hand over the job URL and the confirmed profile. Never a dependency. |

## Slash invocation

`/job-scout find roles for this resume` · `/job-scout anything new since last time?`
