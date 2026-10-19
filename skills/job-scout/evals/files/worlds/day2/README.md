# Replay world: day2

The same four job boards as `../day1`, one week later. Evals E5 and E6 run against it, and
`tests/test_rerun_world.py` checks that the facts below still hold.

This world was **not** recorded live. It is a copy of day1's 32 fixtures with 5 files edited
and 1 file added by hand, so each rerun case happens exactly once. The format is the same as
day1: each file is `sha1(url)[:16].json` holding `{"url", "status", "body"}`, and net.py
replays it.

`profile.json` is not a fixture. It is the brief the user confirmed on day1: the E2 persona
(remote only, US, no pay floor, no sponsorship, exclude Lumenly) with "Product Engineer" as a
title synonym and "Software Engineer" as a title keyword. The day1 search with this brief has
10 candidates; the user was shown 6 of them.

## What the user did on day1

`../../seen-after-feedback.json` is the `seen.json` after day1. `tests/test_rerun_world.py`
builds it by running probe, filter, fetch_jd, a hand-written results.json (cite_check passes),
`state.py seen record`, and then these marks. The test fails if the file and the scripts' output
differ (timestamps aside). Regenerate it with `python3 -m tests.test_rerun_world --write`.

| Job key | Title on day1 | Feedback |
|---|---|---|
| `greenhouse:arizeai:5778086004` | Senior Open Source Design Engineer | saved |
| `ashby:turquoise-health:806f5f93-6eb6-4aea-9483-f8f7458e6730` | Senior Design Engineer | applied |
| `ashby:turquoise-health:87306d91-a18e-490c-b4e6-4758d63b12a1` | Senior Software Engineer, Transactions | dismissed, "too senior" |
| `greenhouse:arizeai:5396420004` | Senior AI Product Engineer, Fullstack | seen |
| `greenhouse:arizeai:5396396004` | Senior AI Product Engineer, Backend | seen |
| `greenhouse:koboldmetals:4286209005` | Frontend Software Engineer | seen |

## Which job shows which case on day2

| Case | Job key | What changed in the fixtures |
|---|---|---|
| New role | `greenhouse:arizeai:6311447004` — Design Engineer, Design Systems (Remote, United States, $175,000–$210,000/yr) | Added to the arizeai board list, plus its single-job fixture `06ac80f73c5dd511.json` (new file) |
| Changed role | `greenhouse:arizeai:5396420004` — title is now "Senior AI Product Engineer, **Frontend**" (was "Fullstack") | Title edited in the arizeai board list and in its single-job fixture `ac933df37636ab23.json` |
| Saved role closed | `greenhouse:arizeai:5778086004` — Senior Open Source Design Engineer | Removed from the arizeai board list; its single-job fixture `87c5f68de429167b.json` now answers 404 |
| Board error | `greenhouse:koboldmetals` board list `34bb9ab6da3f50bf.json` answers HTTP 503 | probe.py reports it under `errors` (not blocked). Its seen role `greenhouse:koboldmetals:4286209005` must **not** be called closed |
| Applied role still open | `ashby:turquoise-health:806f5f93-6eb6-4aea-9483-f8f7458e6730` | Unchanged |
| Dismissed role | `ashby:turquoise-health:87306d91-a18e-490c-b4e6-4758d63b12a1` | Unchanged; hidden on a rerun, back with `--all` |
| Seen, unchanged | `greenhouse:arizeai:5396396004` | Unchanged; hidden on a rerun (`already_seen`), back with `--all` |

The arizeai board list is file `33865125d39df06f.json`. Every other file is exactly the same as
in day1.

Expected script output on the rerun:

- `state.py seen diff`: `changed` = the retitled job, `closed` = the saved job only,
  `applied_open` = the applied job, `saved_open` empty. `new` holds the new job (and every other
  job on the live boards that was never shown, since diff does not apply the brief).
- `filter.py`: candidates are the new job (state `new`) then the changed job (`changed`);
  `removed.already_seen` 1, `removed.dismissed_or_applied` 2. `filter.py --all` brings the
  seen, applied and dismissed jobs back, each tagged with its state.

## Replay it

From the skill folder (`skills/job-scout/`):

```
export JOB_SCOUT_REPLAY_DIR=evals/files/worlds/day2
export JOB_SCOUT_HOME="$(mktemp -d)"
cp evals/files/worlds/day2/profile.json "$JOB_SCOUT_HOME/profile.json"
cp evals/files/seen-after-feedback.json "$JOB_SCOUT_HOME/seen.json"
python3 scripts/probe.py --health
python3 scripts/probe.py --boards greenhouse:koboldmetals,greenhouse:arizeai,ashby:turquoise-health,ashby:reactivemarkets
python3 scripts/state.py seen diff
python3 scripts/filter.py
python3 scripts/filter.py --all
python3 scripts/fetch_jd.py --keys greenhouse:arizeai:6311447004,greenhouse:arizeai:5396420004
```

Always pass `--boards`, as with day1. `python3 scripts/companies.py add "Linear" "Figma"` needs
no fixtures: both are in the seed list, so it makes 0 requests.

If day1 is re-recorded, rebuild this folder from the new day1 files with the same edits, then
update the tables above, the evals, and `tests/test_rerun_world.py`.
