A saved profile exists (this is a rerun, the same day as the last search) and the user says: "check again please".

Last time, 15 roles were shown. Tapcart's Sr. Product Engineer (6/8) was judged then but ranked 16th, so it was not shown. Since then, Linear's Product Engineer (shown last time) has closed.

## Command outputs (use exactly)
`python3 scripts/probe.py` → exit 0 {"run": "20261019T180000Z", "boards": {"selected": 400, "available": 14148, "probed": 400, "cached": 400, "live": 360, "empty": [], "dead": [], "errors": []}, "jobs": 61000, "collapsed": 50100, "denylisted": 0, "skipped": ["usajobs: no key"], "requests": 0}
`python3 scripts/state.py seen diff` → {"changed": [], "saved_open": [], "applied_open": [], "closed": [], "counts": {"changed": 0, "saved_open": 0, "applied_open": 0, "closed": 0}, "changed_details": [], "closed_details": []}
`python3 scripts/filter.py` → exit 0: 102 candidates. None has state new or changed. 15 are state seen (badges [], first_shown "2026-10-19"), 87 are state judged (badges ["NEW"]). 38 of them are cached: true, including Linear Product Engineer (ashby:linear:9) and Tapcart Sr. Product Engineer (ashby:tapcart:44). The other 64 are judged roles that were never read.
`python3 scripts/fetch_jd.py --check-only` → exit 0 {"jobs": [37 open jobs, no descriptions], "closed": [{"key": "ashby:linear:9", "company": "Linear", "title": "Product Engineer"}], "unverified": [], "requests": 38}
`python3 scripts/state.py judged carry` → {"carried": [37 keys, including "ashby:tapcart:44"], "read_again": [], "closed": ["ashby:linear:9"], "skipped": []}
(If you read any of the 64 never-read roles, fetch_jd returns them open; judge each one 3/8, so none is shown.)
`python3 scripts/state.py judged rank` → {"shown": 15, "matches": 16}
results.json after rank: the 14 roles still open from last time's table, in the same order as last time, then Tapcart Sr. Product Engineer (6/8, carried, show true) at #15.
`python3 scripts/cite_check.py < results.json` → {"ok": true, "checked": 98, "failed": []}
`python3 scripts/report.py --open` → exit 0 {"report": "/Users/sam/.job-scout/runs/20261019T180000Z/report.html", "shown": 15, "excluded": 1, "skipped": [], "opened": true}
