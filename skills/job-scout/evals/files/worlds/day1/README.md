# Replay world: day1

A small, offline copy of four real job boards, recorded live on 2026-10-19 (UTC) with
net.py's record mode (`JOB_SCOUT_RECORD_DIR`). Evals E2, E3 and E8 run against it, and
`tests/test_replay_world.py` checks that the facts below still hold.

Each file is `sha1(url)[:16].json` holding `{"url", "status", "body"}`. Nothing is trimmed:
every board list and job description is the full response. 32 files, about 1.4 MB:

- 4 board lists: greenhouse:koboldmetals (32 jobs), greenhouse:arizeai (25),
  ashby:turquoise-health (15), ashby:reactivemarkets (7).
- 25 Greenhouse single-job responses (every job whose title says engineer, developer,
  design, front, software or product), so `fetch_jd.py` can live-check them. Ashby has no
  single-job endpoint; `fetch_jd.py` reads the board list that `probe.py` cached.
- 3 health-check responses (404 = host reachable), so `probe.py --health` passes.

## Which job shows which case

| Case | Job key | Title | Location |
|---|---|---|---|
| US-remote design engineer, refuses sponsorship | `ashby:turquoise-health:806f5f93-6eb6-4aea-9483-f8f7458e6730` | Senior Design Engineer | Remote (US) |
| US-remote design engineer, silent on sponsorship | `greenhouse:arizeai:5778086004` | Senior Open Source Design Engineer | Remote (United States) |
| "Americas" remote (gets the "Americas — check US eligibility" flag) | `greenhouse:koboldmetals:4286209005` | Frontend Software Engineer | Remote, North America |
| Remote limited to a non-US country (removed: `remote_scope`) | `ashby:reactivemarkets:50abf8d2-33fe-40bb-85ba-10a69bec0403` | Senior Frontend Engineer | Remote, UK |
| Bare "Remote" (scope not stated) | `greenhouse:arizeai:6115096004` | Talent Community | Remote |

The refusal sentence in the Turquoise description (E3 quotes it):

> Turquoise does not sponsor employment visas (H-1B, PERM, etc.) or assume sponsorship of
> existing visas for this position.

The Reactive Markets job also refuses UK visa sponsorship. No job in this world is a nursing
role, which is what E8 needs.

## Replay it

From the skill folder (`skills/job-scout/`):

```
export JOB_SCOUT_REPLAY_DIR=evals/files/worlds/day1
export JOB_SCOUT_HOME="$(mktemp -d)"
python3 scripts/probe.py --health
python3 scripts/probe.py --boards greenhouse:koboldmetals,greenhouse:arizeai,ashby:turquoise-health,ashby:reactivemarkets
python3 scripts/filter.py
python3 scripts/fetch_jd.py --keys <keys from filter.py>
```

Always pass `--boards`: without it `probe.py` picks up to 400 boards from companies.csv,
and every board not in this folder fails as a replay miss.

To re-record, delete this folder's JSON files and fetch the same four boards and their
Greenhouse jobs with `JOB_SCOUT_RECORD_DIR` set to this folder. Job ids change over time, so
then update the table above, the evals, and `tests/test_replay_world.py`.
