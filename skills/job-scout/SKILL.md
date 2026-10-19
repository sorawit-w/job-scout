---
name: job-scout
description: >-
  Finds open jobs that fit the user's resume by reading employer job boards directly
  (Greenhouse, Ashby, Lever, SmartRecruiters, Workday; USAJOBS with the user's own free key),
  after the user confirms a short search brief. Returns about
  15 roles checked open today, each linked straight to the employer, with fit reasons quoted
  from the job description and honest unknowns ("pay not listed"). Remembers seen, saved,
  applied and dismissed roles so reruns show what's new. Best for tech and startup roles;
  partial coverage of large employers and hospitals.
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
  job-board APIs employers publish (Greenhouse, Ashby, Lever, SmartRecruiters, Workday) and,
  when the user sets their own key, USAJOBS — nothing else.
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
rerun (Phase 9). Show the brief with what changed since last time ("same as last time — change
anything?") instead of re-deriving everything.

## Phase 2 — Search brief and confirmation gate (required)

**Rule: no request reaches any job board until the user confirms or edits the brief.** The one
exception is an explicit "just go" / "skip the questions" / "use your best guess" — and even
then you show the brief, with every assumed value labelled `default`, and proceed in the same
reply. A brief saved on an earlier run was already confirmed: see Phase 9.

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

job-scout is strongest for tech and startup roles (Greenhouse, Ashby, Lever). It also reads
SmartRecruiters and the Workday sites of a few thousand large employers and hospital systems —
only the companies on its list, so coverage there is partial. US federal jobs need the user's own
USAJOBS key (Phase 4). Trades, teaching, small local employers and most state or city jobs are
still thin. When the target roles sit mostly in those areas, say so **in the brief**: "Many
employers in your field use hiring tools I can't read, so results may be thin." Offer to search
anyway; never pad the results with weak matches to compensate.

### Optional: work style

On a first run (no saved profile), once the user confirms the brief — not on "just go" — ask
**once** before searching, in one numbered message (outside the 5-question budget).
Every topic is optional; offer exactly these choices: 1. Meetings: async-first / meetings OK ·
2. On-call: none / OK · 3. Travel: none / some / lots OK · 4. Autonomy: high / guided ·
5. Company stage: startup / growth / established. Say once that these never change fit, rank or
what is shown — each role shows what its posting says (matches / doesn't match / not stated).
Save the picks as `work_style` (`{}` for "skip"), so it is never asked again; "change my work
style" edits it any time (from the next search on). The questions are about the job, not the
person: if the user gives a personal reason ("no travel — I have kids"), store only the choice;
never record or repeat the reason. "Only show async companies" is a dealbreaker, not a signal: offer `dealbreakers` instead.
On "just go", list it as an optional follow-up. On a rerun without it, offer it once after the
results; if the user moves on, save `{}`.

### Save the confirmed brief

Save it with `python3 scripts/state.py profile save --stdin`, in the format and with the field
rules in `references/profile.md` (read it before saving). **claude.ai:** files do not persist
between conversations. After saving, tell the user once and offer the profile as a code block
they can paste next time.

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
    `api.ashbyhq.com` and `api.lever.co` (plus `api.smartrecruiters.com`, `*.myworkdayjobs.com`
    and, for USAJOBS, `data.usajobs.gov` — without them those boards are skipped as errors).
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
- It picks boards by the brief's field: tech briefs get the tech boards first, other briefs get
  Workday and SmartRecruiters first, so neither crowds the other out of the cap.
- **Search words leave the machine.** Workday and USAJOBS are searched with the brief's target
  job titles; nothing else from the brief is sent anywhere.
- **USAJOBS (US federal jobs) is opt-in.** If probe.py's `skipped` says `usajobs: no key` and the
  user's field includes government work, say once: "Federal jobs need your own free USAJOBS
  key: request one at https://developer.usajobs.gov/apirequest/, then set
  JOB_SCOUT_USAJOBS_KEY and JOB_SCOUT_USAJOBS_EMAIL in your environment." Never ask the user to
  paste the key into the chat; continue without it.

## Phase 5 — Narrow, then read the job descriptions

1. Run `python3 scripts/filter.py`. It applies the confirmed brief deterministically (work mode,
   location, remote scope, level, track, excluded companies and titles, pay floor) and prints
   `counts`, ranked `candidates` (each `strong` or `borderline`, with `flags`) and up to 5
   `near_misses`. With **zero candidates**, skip steps 2–3 and Phase 6, explain using
   `counts.removed` (see `references/output-format.md` §4) — never pad — then still write the
   report as in Phase 7. On a rerun, zero candidates usually means nothing new: follow Phase 9
   instead.
2. Choose **up to 40** candidates whose descriptions are worth reading: all plausible `strong`
   ones, then `borderline` titles that could be the target role in substance (a title like
   "Software Engineer, Product" may be exactly a design-engineering job). Skip ones the title
   already rules out.
3. Run `python3 scripts/fetch_jd.py --keys <key1>,<key2>,...`. It re-checks each job on the
   employer's board (the live check) and returns `jobs` (open, with a trimmed `jd`), `closed`,
   and `unverified`. **Show only `open` jobs**; never present a closed or unverified job as open.
   Exit 4 → the request cap stopped the checks: show the open ones and say the rest couldn't be
   checked.

## Phase 6 — Judge fit, with quotes

Read `references/rubric.md` and follow it: four pass/fail gates (location, sponsorship, pay,
exclusions), four 0–2 scores, a quote from the job description for every claim, and — with a
saved `work_style` — display-only work-style signals (rubric §4). Write the result to
`<run dir>/results.json`, then run:

```
python3 scripts/cite_check.py < <run dir>/results.json
```

If it reports `failed` claims, re-read the description and fix or delete each one, then run it
again until `"ok": true`. Why: a confident claim the description doesn't support is exactly the
failure job-scout exists to prevent.

## Phase 7 — Show the results

Follow `references/output-format.md`: one coverage line, the seven-column table (employer links
only), one notes line per row with the quoted why/risk and "open since", 3–5 "close but
excluded" lines, then the feedback prompt.

Then write the HTML report, **before** Phase 8's `seen record`: `python3 scripts/report.py --open`
(leave out `--open` on claude.ai, in Codex, or with no local browser). Give the user the `report`
path it prints. The report is an extra: the chat table above always comes first. Details:
`references/output-format.md` §7.

## Phase 8 — Remember and take feedback

Right after showing the results, run `python3 scripts/state.py seen record` so the shown roles
count as seen next time. Then act on the user's feedback, one command per role (keys come
from results.json):

```
python3 scripts/state.py seen mark <key> saved
python3 scripts/state.py seen mark <key> applied
python3 scripts/state.py seen mark <key> dismissed --reason="too senior"
```

Confirm each in one line ("Saved #1 — Vercel, Design Engineer"). A line pasted from the report,
like `save 3 (Vercel, Design Engineer)`, names its role: act on the named role, and ask if the
number points at a different one. If feedback implies a brief
change ("I keep dismissing hybrid roles", three dismissals for the same reason), propose the
change and save it only after the user agrees — never change the brief silently.

**Adding companies.** When the user names companies to always check ("also check Linear and
Figma"), follow `references/companies.md`: it runs `scripts/companies.py add`, confirms guessed
boards with the user, and takes a Workday careers URL with `--board`.

## Phase 9 — Reruns

A saved profile means a rerun (Phase 1). The saved brief was confirmed on an earlier run, so
show it as "same as last time" and search in the same reply. If the user's message changes
anything in it ("I'm open to hybrid now"), show the changed brief and confirm it first, as in
Phase 2. After Phases 3–4 run `python3 scripts/state.py seen diff` and
`python3 scripts/filter.py` (on a rerun it shows only new, changed and saved roles; `--all`
shows everything). Lead with what moved:

- **New** roles first (mark them `NEW`), then **changed** ones — say what changed, from
  `changed_details` (`before` → `after`: title, pay or locations).
- **Saved or applied, still open** (`saved_open`, `applied_open`) — a short list, so nothing
  they cared about is lost.
- **Closed since last time** — the saved or applied roles in `closed_details` that are gone (from
  the board, or found gone by the live check).
  A role closes only when a board checked successfully this run no longer lists it, or its
  live check found the posting gone; never call a role closed because a board failed.

With nothing new, say so in one line and show the saved-or-applied list. End every rerun with
`python3 scripts/report.py --open` (as in Phase 7), then `python3 scripts/state.py seen record` —
also when nothing was new — so closures are remembered and not reported again next time.

**claude.ai:** files do not persist there. At the end, offer the profile and the saved/applied
roles (title, company, link) as one block the user can paste next time.

## Cross-skill integration

| Skill | Relationship |
|---|---|
| [`ghostwriter`](https://github.com/sorawit-w/agent-skills) *(if installed)* | Drafts outreach and recruiter messages for a role job-scout found. Hand over the job URL and the confirmed profile. Never a dependency. |

## Slash invocation

`/job-scout find roles for this resume` · `/job-scout anything new since last time?`
