# Privacy

job-scout runs on your machine (or in your agent's sandbox). It has no server and sends no
telemetry. This page lists everything it sends and everything it stores.

## What leaves your machine

Only requests to public job-board APIs. Each request carries the User-Agent
`job-scout/<version> (+https://github.com/sorawit-w/job-scout)`, except USAJOBS: its API
requires your registered email as the User-Agent, so USAJOBS requests send that instead.

| Host | What is requested | Anything from you in it? |
|---|---|---|
| `boards-api.greenhouse.io` | A company's job list, or one job | No |
| `api.ashbyhq.com` | A company's job list | No |
| `api.lever.co` | A company's job list, or one job | No |
| `api.smartrecruiters.com` | A company's job list, or one job | No |
| `<company>.<wdN>.myworkdayjobs.com` | A title search on that company's board, or one job | **Your target job titles** (up to 3 per board) |
| `data.usajobs.gov` (only with your key) | A title search, or one job | **Your target job titles**, plus your key and email as request headers, which the USAJOBS API requires |

The target titles are the `target_roles` and `title_synonyms` in your brief, for example
"Registered Nurse". Nothing else from your resume or brief is sent: not your name, contact
details, employer, pay, location or work history.

The skill's agent (Claude, Codex or another model) reads your resume in the conversation. That
is governed by the agent provider's own privacy terms, not by job-scout.

## What is stored, and where

Everything lives in `~/.job-scout/` (or the folder in `JOB_SCOUT_HOME`):

| File | What it holds |
|---|---|
| `profile.json` | Your confirmed search brief. The schema rejects unknown fields, so protected traits can't be saved. |
| `seen.json` | Roles you have seen, saved, applied to or dismissed (with your reason), so reruns show what is new. |
| `companies.csv` | Companies you added. |
| `cache/` | Job lists from each board, kept 6 hours. Errors are never cached. |
| `runs/<id>/` | One folder per search: jobs, candidates, descriptions, results. Only the newest 3 are kept. |

Your resume file is never copied into `~/.job-scout/`. To delete everything, delete the folder.

On claude.ai, files don't persist between conversations. The skill offers your brief and saved
roles as a block you can paste next time.

## USAJOBS key

The key is read from the `JOB_SCOUT_USAJOBS_KEY` and `JOB_SCOUT_USAJOBS_EMAIL` environment
variables. It is sent only as request headers to `data.usajobs.gov`, never put in a URL, never
written to disk, and never recorded in test fixtures. The skill never asks you to paste it into
a chat.
