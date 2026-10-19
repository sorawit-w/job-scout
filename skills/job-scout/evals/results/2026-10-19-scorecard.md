# Scorecard — frontend persona, 49 eval boards, 2026-10-19

**Persona:** senior frontend / design engineer near Pasadena, CA; remote in the US or hybrid;
would relocate within the US for hybrid or onsite; Senior/Staff; individual contributor
(`skills/job-scout/evals/files/persona-frontend.md`).

**Data:** one live snapshot of the 49 eval boards (`scripts/relabel_ground_truth.py snapshot`):
46 live, 3 empty, 7,800 jobs → 6,439 after merging regional duplicates. job-scout replays the
snapshot for probing; its live check (`fetch_jd.py`) ran against the real boards the same day.
jobscope (commit `0e3e0e2`, same config as M0 run B: 7 titles, 49 boards + The Muse) ran live the
same day.

**Answer key:** `evals/ground_truth/2026-10-19.json` — **two-model consensus, not human-labelled.**
A blind, shuffled pool of 433 roles (broad title net ∪ previous ground truth ∪ job-scout candidates
∪ jobscope results) was labelled by Codex (all 433, two passes); Gemini 4 Argon (high) labelled the
178 Codex Strong/Maybe rows, the 15 previous ground-truth roles and 30 sampled Codex No rows, blind
to Codex. **Strong (33)** = both Strong; **uncertain (115)** = any disagreement or double Maybe.
Gemini agreed with 30 of 31 sampled Codex No. Both judges' labels and reasons:
`evals/ground_truth/2026-10-19.judges.json`.

## Results (strict key: 33 roles)

Two full live runs of the skill (fresh agent, SKILL.md followed as written, brief pre-confirmed);
run 2 used the filter after the relevance-ranking fix below.

| Stage | job-scout run 1 | job-scout run 2 | jobscope |
|---|---|---|---|
| Kept / candidates | 27 / 33 in the 150 shown to the agent | **30 / 33** | 21 / 33 in all 432 roles kept |
| Shortlist — the agent's 40 picks, live-checked | **26 / 33** | **26 / 33** | — |
| Final list shown (top 15) | **13 / 33**; 13 of 15 shown are in the key | **13 / 33**; 13 of 15 in the key | **2 / 33** in its top 15 by score |
| Shown roles open on a live check | 15 / 15 (40 / 40 shortlist) | not checked |
| Links straight to the employer | 100% | not measured (M0: 81% for run B) |
| Exact duplicates | 0 | 0 |

**Loose key (strict + uncertain, 148 roles):** all 15 job-scout roles shown are in it (both
runs); 7 of jobscope's top 15 are.

**Against the HANDOFF §11 bar** (shortlist ≥ 15/18 on the old key ≈ 83%): the shortlist reaches
26/33 (79%) on the new, larger key — close, a little short. The roles still missed have generic
titles ("Staff Software Engineer, Product") that the agent cannot judge from the title when it picks
40; 31 strong titles already take most of the 40 slots. Follow-up: let the agent read up to 60 when
there are many strong candidates.

The top-15 number cannot exceed 15/33: the key holds more strong roles than one screen shows. The
fair top-15 reading is precision — how many shown roles are real fits.

## Baseline without the skill (V7)

Covered in M0 (`docs/m0/M0_REPORT.md`): a plain agent with web search surfaced 2 of 18 strong roles,
and the Indeed / Dice / ZipRecruiter connectors 0–6% with no direct employer links. Not re-run on
the new key.

## What the evaluation changed (fix loop, V8)

Found by scoring against this key, each fixed test-first:
- a single common word ("systems", "platform") no longer makes a borderline title match;
- strong title matches need the role's words together ("AV Engineer, Builds and Design" is not a
  design engineer);
- an engineering title with a generic name is kept when its description names ≥3 of the brief's
  title keywords;
- candidates rank by description relevance before date, so relevant borderline titles survive the
  150 limit (27 → 30 of 33 in the default list);
- the labelling sheet shows the posting a US-based person can take when a role is posted once per
  region.

## Limits

- One persona, one day, one run per tool. jobscope's score depends on its title list (M0's config,
  reused unchanged).
- The key is model consensus. A human re-label (the original V4 plan) would make it stronger.
- Unjudged rows: candidates outside the labelled pool count as not-strong.
