# Output format — what the user sees

Write for anyone, not just engineers: no "ATS", "slug", "JSON" or "API".

## 1. One line of coverage first

Open the results with this line — no summary sentence before it. (On a "just go" run the brief
comes first in the same reply, then this line.)

`Checked N of M company job boards (K jobs open today). Best for tech and startup roles.`

On a rerun, count what moved instead, so a short list doesn't read as "only K jobs exist":
`Checked N of M company job boards — K new or changed since last time.`
Use `boards.probed` and `boards.available` from probe.py and the number of open jobs from
fetch_jd.py. If the user's field is mostly outside tech, say coverage was thin here too.

## 2. The table — seven columns

```
| # | Role | Company | Mode · where | Pay | Fit | Link |
|---|------|---------|--------------|-----|-----|------|
| 1 | Design Engineer | Vercel | Remote · US | $208k–$312k/yr | 7/8 | [Apply](https://job-boards.greenhouse.io/vercel/jobs/6129441004) |
```

- **Link** is the employer's own job page (`url` from the data) — never an aggregator, never a
  search page.
- **Pay** from the structured `comp`. A range found only in the description may be shown if it is
  also a quoted `why` or `risk` item in results.json (so cite_check verifies it); otherwise
  `pay not listed`. Never estimate.
- **Fit** is the rubric `total` out of 8.

Under the table, one notes line per row, keyed by `#`:

```
1. Why: "own and evolve our design system" · Risk: sponsorship not stated · Open since 2026-09-15
```

- Why/Risk use the cited quotes from results.json (short ones; trim long quotes with "…" only
  at the ends, never in the middle).
- Add `Open since <first_published>` for every row and `(open over 90 days)` when flagged —
  long-open roles stay visible; they are often still hiring.
- Add `NEW` for roles whose `state` from filter.py is `new` on a rerun, and say what changed
  for `changed` ones ("pay now listed", "title changed").

## 3. Close but excluded — 3 to 5 rows

```
Close but excluded:
- Staff Design Engineer, Ashby — remote limited to the EU ("Remote - European Union")
- Senior Frontend Engineer, Harvey — pay tops out below your floor ($180k–$195k)
```

Pick the closest misses from filter.py's `near_misses` and from rows you scored but excluded.
One line each, one reason each, so the user can spot a filter that's too tight.

## 4. When nothing matches

On a rerun, zero candidates usually means nothing new: follow SKILL.md Phase 9 (say so in one
line, show the saved and applied roles still open) instead of the explanation below.

Say so plainly and name the filter that removed the most jobs, using filter.py's
`counts.removed` (e.g. "Most roles were removed by your remote scope (US only) — 212 of 640.
Want me to include Americas-wide remote roles?"). Never fill the table with weak matches.

## 5. End with the feedback prompt

Skip it when no roles are shown; end with the question from §4 instead.

```
Tell me what to do with any of these — "save 1", "applied 3", "dismiss 2: too senior".
I'll remember them next time and show you only what's new.
```

## 6. claude.ai only

Files don't persist between conversations there. Offer the saved profile and the saved/applied
roles (title, company, link) as one code block the user can paste next time.

## 7. The HTML report

After the chat output, run `python3 scripts/report.py --open` (SKILL.md Phase 7, and at the end
of every rerun). It writes `report.html` in the run folder: the brief, the coverage line, a
table with one row per shown role (the same ranks as the chat table) whose details open on
click (quotes, score meters, gates, copy buttons) — inline, or in a side pane on wide screens —
the saved/applied and closed lists on a rerun, and the close-but-excluded lines. It reads the run
files, so it needs `results.json` from Phase 6 when roles were judged; with none (nothing new,
or zero candidates) it still writes the "nothing new" or zero-results page.

- Run it **before** `state.py seen record`: after `record`, closed roles no longer show.
- Always say the path from its output (`"report"`). With `--open`, `"opened": false` means no
  browser was found: just give the path.
- `"skipped"` lists results.json keys the run doesn't know. Fix those rows rather than ignore them.
- Exit 2 (no jobs or candidates in the run) → say in one line that there is no report for this run.
- **claude.ai:** leave out `--open`; share the file as a download if the environment offers one.
- The page makes no network requests and keeps no state; the copy buttons only copy a line such
  as `save 3 (Vercel, Design Engineer)` for the user to paste back here.
