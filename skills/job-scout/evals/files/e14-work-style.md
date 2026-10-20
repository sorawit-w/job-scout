The brief was confirmed and saved earlier. The saved profile includes:
`"work_style": {"meetings": "async", "travel": "none", "stage": "startup"}`

The search already ran in this conversation:

`python3 scripts/probe.py` → exit 0 {"run": "20261019T120000Z", "boards": {"selected": 400, "available": 14148, "probed": 400, "cached": 0, "live": 352, "empty": [], "dead": [], "errors": []}, "jobs": 61000, "collapsed": 50100, "denylisted": 0, "skipped": ["usajobs: no key"], "requests": 410}
`python3 scripts/filter.py` → exit 0, 3 candidates
`python3 scripts/fetch_jd.py --keys ...` → exit 0, 3 jobs open

You already judged fit (gates all pass or unknown; totals: role 1 = 7, role 2 = 7, role 3 = 6). The
three job descriptions, word for word (only these passages mention work style):

1. `greenhouse:northwind:101` — Northwind, Design Engineer, Remote US, $180k–$210k/yr
   "Our team works async-first and writes decisions down instead of holding meetings. This role
   requires no travel. We're an early-stage startup backed by our seed investors."

2. `greenhouse:stripe:202` — Stripe, Frontend Engineer, Remote US, $200k–$240k/yr
   "You'll join daily standups at 9am Pacific with the whole team. Travel up to 25% of the time to
   customer sites." (Nothing else in the description mentions the company's stage or size.)

3. `ashby:ledgerline:303` — Ledgerline, UI Engineer, Remote US, pay not listed
   "Ledgerline is a public company listed on the NYSE." (Nothing about meetings or travel.)

## Command outputs still to come (use exactly)
`python3 scripts/cite_check.py < results.json` → exit 0 {"ok": true, "checked": 18, "failed": []}
`python3 scripts/report.py --open` → exit 0 {"report": "/Users/sam/.job-scout/runs/20261019T120000Z/report.html", "shown": 3, "excluded": 0, "skipped": [], "opened": true}
`python3 scripts/state.py seen record` → exit 0 {"recorded": 3}

---

The user is in Claude Code on their laptop. Write the `style` part of each row in results.json
(show the JSON for the three rows' `style` arrays), then show the results to the user.
