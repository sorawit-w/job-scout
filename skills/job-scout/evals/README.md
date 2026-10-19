# job-scout evals

Test prompts for the skill, with assertions a grader can check. `evals.json` holds them all.
Everything here is for maintainers: the release zip (`build_release.py`, planned for M6) leaves
the `evals/` folder out.

## The evals

"Stated-intent" means a fresh agent reads SKILL.md and the prompt and says what it would do,
step by step; a skill-evaluator run grades that against the assertions. "Live" means a
skill-creator run executes the skill with its scripts, against a replay world when one is listed.

| ID | What it checks | Persona / file | World | How to run |
|---|---|---|---|---|
| E1 | Gate fires before any search; asks work mode, pay, sponsorship | persona-frontend.md | none | stated-intent |
| E2 | Remote US: UK-only remote removed, Americas flagged, employer links | persona-frontend.md | day1 | live |
| E3 | Needs sponsorship: refusal quoted or job excluded, silence labelled | persona-frontend.md | day1 | live |
| E4 | "Just go": brief shown with labelled defaults, no stop | persona-frontend.md | none (day1 lets `--health` pass offline) | live |
| E5 | Rerun: new first, changed explained, applied not new, saved role closed, failed board never closes | day2/profile.json + seen-after-feedback.json | day2 | live |
| E6 | Add Linear and Figma from the seed list | same as E5 | day2 | live |
| E7 | Cover letter request: no search, out of scope | none | none | stated-intent |
| E8 | Nurse: thin coverage said honestly, no padding | persona-nurse.md | day1 | live |
| E9 | Chat only, non-developer: gate works, no jargon | persona-marketer-chat.md (typed in chat, not attached) | none | stated-intent |
| E10 | Data analyst, remote US: asks pay and sponsorship; analytics roles, not data engineering | persona-data-analyst.md | none | stated-intent |
| E11 | PM on the IC track: keeps "Product Manager" titles, never the manager track | persona-pm.md | none | stated-intent |

All persona files are in `files/`. They are synthetic people with fictional employers and no
protected attributes. Any eval can also run live; the gate evals (E1, E7, E9–E11) stop before
any search, so stated-intent is enough for them.

## Replay the worlds

The worlds are offline copies of four job boards, so live evals make no network calls. Read
`files/worlds/day1/README.md` and `files/worlds/day2/README.md` for which job shows which case.
From the skill folder (`skills/job-scout/`):

```
export JOB_SCOUT_REPLAY_DIR=evals/files/worlds/day1     # or day2
export JOB_SCOUT_HOME="$(mktemp -d)"                     # always a new, empty temp folder
# day2 only — the brief and feedback from last week:
cp evals/files/worlds/day2/profile.json "$JOB_SCOUT_HOME/profile.json"
cp evals/files/seen-after-feedback.json "$JOB_SCOUT_HOME/seen.json"
python3 scripts/probe.py --health
python3 scripts/probe.py --boards greenhouse:koboldmetals,greenhouse:arizeai,ashby:turquoise-health,ashby:reactivemarkets
```

Always pass `--boards`. Without it, `probe.py` picks up to 400 boards and every board that is
not in the world fails as a replay miss. `tests/test_replay_world.py` and
`tests/test_rerun_world.py` check that the worlds still show the cases the evals need.

## Recall and ground truth

- Ground truth today: `docs/reference/ground_truth_2026-10-18.json` (18 strong-fit roles for
  the frontend persona on the 49-board seed).
- After the M5 re-label: `skills/job-scout/evals/ground_truth/<date>.json`, one file per eval
  day. Roles open and close, so re-label on the day you score.
- Score a run with `scripts/score_run.py`:

```
python3 scripts/score_run.py --gt <ground truth file> --run <run dir> --stage results --top 15
```

A ground-truth role counts as found when any scored row, or any entry in that row's
`variants[]`, has the same board, the exact title and the same first-published date. A role
whose board was not probed is reported as "not probed", not as missed. The script also reports
employer-link share, exact duplicates and open share. The target is in `docs/HANDOFF.md` §11:
at least 15 of 18.
