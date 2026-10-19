# Fit rubric — how to judge each shortlisted job

Judge only the jobs `fetch_jd.py` returned as `open`, using the user's confirmed profile and the
job description text in that output (`jd`). The full text behind it is in `<run>/jds.json`.

**Every claim about a job must quote its job description.** A claim you can't quote is a guess:
leave it out, or use one of the fixed unknown labels below. `scripts/cite_check.py` verifies every
quote against the full description before anything is shown to the user.

## 1. Gates — pass / fail / unknown

A failed gate removes the job from the table (it may appear in "close but excluded").
An unknown gate keeps the job and shows the unknown label.

| Gate | Fail when | Unknown label |
|---|---|---|
| **Location / mode** | The description clearly rules the user out: onsite-only in another city, remote limited to countries outside the user's remote scope, required relocation they didn't accept. Quote it. | `location unclear` |
| **Sponsorship** | The user needs sponsorship (`needs_sponsorship: "yes"`) and the description says it won't sponsor, or requires citizenship / permanent residency. Quote it. (If the user said `no` or `undisclosed`, this gate always passes.) | `sponsorship not stated` |
| **Pay floor** | Listed pay (structured `comp`, or a pay range quoted from the description) tops out below the user's floor, in the same currency and interval. Quote it, or cite the structured range. Also fail when the user chose `hide_no_pay` and the job has neither. | `pay not listed` |
| **Exclusions** | The description shows the job is in one of the user's `industries_exclude`, or hits one of their `dealbreakers`. Quote it as a `risk` item. A score total never overrides this gate. | — (not stated = pass; never guess) |

Never infer a gate from the company's reputation, size, or what "usually" happens.

## 2. Scores — 0, 1 or 2 each

| Score | 2 | 1 | 0 |
|---|---|---|---|
| **Role** | The job is one of the target roles in substance (what you'd do day to day), whatever its title. | Adjacent: overlaps heavily but leans elsewhere (e.g. full-stack, backend-leaning, for a frontend target). | A different job family. |
| **Skills** | The description's must-haves are mostly skills the resume shows. | About half overlap, or the key skill is a near neighbour. | Little overlap, or a hard requirement the user clearly lacks. |
| **Level** | The level (title or years asked) matches the user's seniority. | One step off (e.g. Senior for a Staff, Staff for a Senior). | Two or more steps off. |
| **Domain** | Matches `industries_prefer`, or the user stated no preference. | Neutral. | In `industries_exclude` (that also fails the Exclusions gate). |

`total` = sum of the four (0–8).

**Show a job when no gate failed and `total` ≥ 5.** Rank by `total`, then remote scope matching
exactly before flagged ones, then newest "open since". Show at most `result_count` (default 15).
Fewer good matches is the honest answer; never pad to reach the count.

## 3. Write `results.json`

One row per judged job, in your ranked order, including jobs you excluded (they feed the
"close but excluded" list and cite_check verifies their quotes too):

```json
{"rows": [
  {"key": "greenhouse:vercel:6129441004",
   "gates": {"location": "pass", "sponsorship": "unknown", "pay": "pass", "exclusions": "pass"},
   "scores": {"role": 2, "skills": 2, "level": 1, "domain": 2},
   "total": 7,
   "show": true,
   "why":  [{"text": "Design-systems ownership is the core of the role",
             "quote": "own and evolve our design system"}],
   "risk": [{"text": "sponsorship not stated", "quote": null}]}
]}
```

- `quote` is copied **verbatim** from the description, at least 12 characters, contiguous in the
  full text (a quote that jumps across the "…" between trimmed sections will fail).
- `quote: null` is allowed only with `text` exactly `pay not listed`, `sponsorship not stated`, or
  `location unclear`.
- 1–3 `why` items and 0–2 `risk` items per row. Keep `text` short and plain.

Then run `python3 scripts/cite_check.py < results.json`. If it reports failures, fix or delete each
failed claim (re-quote from the description, or drop the claim) and run it again. Never show a
claim that failed, and never edit a quote to match — re-read the description instead.
