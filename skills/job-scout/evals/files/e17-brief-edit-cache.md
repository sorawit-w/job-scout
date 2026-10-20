A saved profile exists (this is a rerun). Last week's search judged 38 roles. The user says: "Here's my updated resume (attached) — I've now led a design-system team. Also, I'm open to hybrid in Austin now. What's out there?"

## Command outputs (use exactly)
`python3 scripts/state.py profile show` → the saved brief (Design Engineer, remote US only, $180k floor, no sponsorship, home base Austin, TX)
The attached resume adds two years as "Design Systems Lead" to the old one; nothing else differs.
`python3 scripts/state.py judged forget` → {"forgot": 38}
`python3 scripts/state.py profile save --stdin` → {"ok": true, "saved": true}
`python3 scripts/probe.py --health` → {"ok": true}
`python3 scripts/probe.py` → exit 0 {"run": "20261026T120000Z", "boards": {"selected": 400, "available": 14148, "probed": 400, "cached": 0, "live": 360, "empty": [], "dead": [], "errors": []}, "jobs": 60000, "collapsed": 49800, "denylisted": 0, "skipped": ["usajobs: no key"], "requests": 420}
`python3 scripts/filter.py` → exit 0: 52 candidates, every one with "cached": false (15 seen, 23 judged, 14 new).
