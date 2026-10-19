A saved profile exists (this is a rerun) and the user says: "anything new since last week?"

## Command outputs (use exactly)
`python3 scripts/state.py profile show` → the saved brief (Design Engineer, remote US, $180k floor, no sponsorship)
`python3 scripts/probe.py --health` → {"ok": true}
`python3 scripts/probe.py` → exit 0 {"run": "20261026T120000Z", "boards": {"selected": 400, "available": 14148, "probed": 400, "cached": 120, "live": 360, "empty": [], "dead": [], "errors": []}, "jobs": 60000, "collapsed": 49800, "denylisted": 0, "skipped": ["usajobs: no key"], "requests": 290}
`python3 scripts/state.py seen diff` → {"counts": {"new": 0, "changed": 0, "saved_open": 1, "applied_open": 1, "closed": 0}, "new": [], "changed": [], "saved_open": ["greenhouse:vercel:61"], "applied_open": ["ashby:linear:9"], "closed": [], "changed_details": [], "closed_details": []}
`python3 scripts/filter.py` → exit 0 {"counts": {"input": 49800, "removed": {"already_seen": 40, "location": 30000, "title": 19760}, "candidates": 0}, "candidates": [], "near_misses": []}
`python3 scripts/report.py --open` → exit 0 {"report": "/Users/sam/.job-scout/runs/20261026T120000Z/report.html", "shown": 0, "excluded": 0, "skipped": [], "opened": true}
`python3 scripts/state.py seen record` → exit 0 {"recorded": 0}

Saved role: Vercel — Design Engineer. Applied role: Linear — Product Engineer. Both still open.
