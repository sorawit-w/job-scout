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
| E12 | HTML report after the chat results, before `seen record`; path given | e12-report.md | none | stated-intent |
| E13 | Rerun with nothing new: one line above the full ranked list, judgments carried, report written | e13-rerun-nothing-new.md | none | stated-intent |
| E14 | Work-style signals quoted, "not stated" when silent, never move a role | e14-work-style.md | none | stated-intent |
| E15 | First confirmed brief asks the optional work-style question before searching | e15-work-style-ask.md | none | stated-intent |
| E16 | A judged role that was cut re-enters the top N badged NEW; cached roles carried, not read | e16-judged-role-enters.md | none | stated-intent |
| E17 | A new resume and a brief edit invalidate every cached judgment | e17-brief-edit-cache.md | none | stated-intent |
| E18 | A carried quote that fails cite_check forces a fresh judgment | e18-carried-quote-fails.md | none | stated-intent |
| E19 | claude.ai: no-memory notice said once; the paste block keeps saved and dismissed roles and restores them | e19-claude-ai-memory.md | none | stated-intent |

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

- Current answer key: `skills/job-scout/evals/ground_truth/2026-10-19.json` — 33 strong roles
  (plus 115 uncertain) for the frontend persona on the 49-board seed, by two-model consensus;
  its `labelled_by` field says how. Results: `evals/results/2026-10-19-scorecard.md`.
- It matches the snapshot `evals/snapshots/2026-10-19/` (gitignored; rebuild with
  `scripts/relabel_ground_truth.py snapshot`). Roles open and close, so a new eval day needs a new
  snapshot and a new key (`relabel_ground_truth.py sheet` → label → `import`).
- `docs/reference/ground_truth_2026-10-18.json` is the older M0 key (18 roles), kept for history.
- Score a run with `scripts/score_run.py`:

```
python3 scripts/score_run.py --gt <ground truth file> --run <run dir> --stage results --top 15
```

A ground-truth role counts as found when any scored row, or any entry in that row's
`variants[]`, has the same board, the exact title and the same first-published date. A role
whose board was not probed is reported as "not probed", not as missed. The script also reports
employer-link share, exact duplicates and open share. The target is in `docs/HANDOFF.md` §11:
at least 15 of 18.
