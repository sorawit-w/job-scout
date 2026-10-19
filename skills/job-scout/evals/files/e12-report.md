The brief was confirmed and saved earlier. The search already ran in this conversation:

`python3 scripts/probe.py --health` → {"ok": true}
`python3 scripts/probe.py` → exit 0 {"run": "20261019T120000Z", "boards": {"selected": 400, "available": 14148, "probed": 400, "cached": 0, "live": 352, "empty": [], "dead": [], "errors": []}, "jobs": 61000, "collapsed": 50100, "denylisted": 0, "skipped": ["usajobs: no key"], "requests": 410}
`python3 scripts/filter.py` → exit 0, 42 candidates
`python3 scripts/fetch_jd.py --keys ...` → exit 0, 15 jobs open, 2 closed
You wrote results.json (15 rows shown, 4 excluded) and `python3 scripts/cite_check.py < results.json` → {"ok": true, "checked": 61, "failed": []}

## Command outputs still to come (use exactly)
`python3 scripts/report.py --open` → exit 0 {"report": "/Users/sam/.job-scout/runs/20261019T120000Z/report.html", "shown": 15, "excluded": 4, "skipped": [], "opened": true}
`python3 scripts/state.py seen record` → exit 0 {"recorded": 15}

---

The user is in Claude Code on their laptop. Show the results now. (Write the chat table with placeholder rows like "| 1 | … |" — the point is the order of steps and what you tell the user.)
