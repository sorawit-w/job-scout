A saved profile exists (this is a rerun) and the user says: "anything new since last week?"

## Command outputs (use exactly)
`python3 scripts/state.py profile show` → the saved brief (Design Engineer, remote US, $180k floor, no sponsorship)
`python3 scripts/probe.py --health` → {"ok": true}
`python3 scripts/probe.py` → exit 0 {"run": "20261026T120000Z", "boards": {"selected": 400, "available": 14148, "probed": 400, "cached": 120, "live": 360, "empty": [], "dead": [], "errors": []}, "jobs": 60000, "collapsed": 49800, "denylisted": 0, "skipped": ["usajobs: no key"], "requests": 290}
`python3 scripts/state.py seen diff` → {"changed": [], "saved_open": ["greenhouse:vercel:61"], "applied_open": ["ashby:linear:9"], "closed": [], "counts": {"changed": 0, "saved_open": 1, "applied_open": 1, "closed": 0}, "changed_details": [], "closed_details": []}
`python3 scripts/filter.py` → exit 0 {"counts": {"input": 49800, "removed": {"dismissed_or_applied": 1, "location": 30000, "title": 19796}, "candidates": 3}, "candidates": [
 {"key": "greenhouse:vercel:61", "company": "Vercel", "title": "Design Engineer", "where": "Remote - US", "mode": "remote", "since": "2026-10-01", "pay": "$208,000–$312,000/yr", "match": "strong", "flags": [], "state": "saved", "badges": ["SAVED"], "first_shown": "2026-10-19", "changes": [], "cached": true},
 {"key": "ashby:ramp:7", "company": "Ramp", "title": "Product Engineer, Design Systems", "where": "Remote - US", "mode": "remote", "since": "2026-10-03", "pay": "$190,000–$230,000/yr", "match": "strong", "flags": [], "state": "seen", "badges": [], "first_shown": "2026-10-19", "changes": [], "cached": true},
 {"key": "greenhouse:retool:3", "company": "Retool", "title": "Frontend Engineer", "where": "Remote - US", "mode": "remote", "since": "2026-09-20", "pay": "pay not listed", "match": "strong", "flags": [], "state": "judged", "badges": ["NEW"], "first_shown": null, "changes": [], "cached": true}],
 "near_misses": []}
`python3 scripts/fetch_jd.py --check-only` → exit 0 {"jobs": [3 jobs, all open, no descriptions], "closed": [], "unverified": [], "requests": 3}
`python3 scripts/state.py judged carry` → {"carried": ["greenhouse:vercel:61", "ashby:ramp:7", "greenhouse:retool:3"], "read_again": [], "closed": [], "skipped": []}
`python3 scripts/state.py judged rank` → {"shown": 2, "matches": 2}
`python3 scripts/cite_check.py < results.json` → {"ok": true, "checked": 7, "failed": []}
results.json after rank, in order: Vercel Design Engineer (7/8, show true, why: "own and evolve our design system"), Ramp Product Engineer, Design Systems (6/8, show true, why: "build our component library"), Retool Frontend Engineer (4/8, show false: the role is mostly backend).
`python3 scripts/report.py --open` → exit 0 {"report": "/Users/sam/.job-scout/runs/20261026T120000Z/report.html", "shown": 2, "excluded": 1, "skipped": [], "opened": true}
`python3 scripts/state.py seen record` → exit 0 {"inserted": 0, "updated": 2, "judged": 1, "missing": 0, "closed": 0, "reopened": 0, "pruned": 0}

Saved role: Vercel — Design Engineer. Applied role: Linear — Product Engineer. Both still open.
