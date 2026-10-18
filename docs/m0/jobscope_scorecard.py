# Score a jobscope _run.json against the 18 ground-truth roles (re-checked open 2026-10-18).
# Usage: python3 jobscope_scorecard.py runA.json runB.json
# Match = same board slug + exact ATS title + same first-published date.
import json, sys
GT = [("replit","Design Engineer","2026-10-16"),
 ("elevenlabs","Full-Stack Engineer (Frontend Leaning) - Studio","2026-10-09"),
 ("openai","Frontend Software Engineer, ChatGPT Space","2026-10-08"),
 ("ramp","Design Systems Lead","2026-09-30"),
 ("vapi","Member of Technical Staff, Frontend","2026-09-22"),
 ("ramp","Software Engineer, Frontend, Growth","2026-09-21"),
 ("vercel","Design Engineer","2026-09-15"),
 ("affirm","Senior Software Engineer, Frontend (Auth Experiences)","2026-09-10"),
 ("perplexity","Member of Technical Staff (Software Engineer, Design System)","2026-08-11"),
 ("harvey","Frontend Platform Engineer","2026-07-31"),
 ("ramp","Design Engineer","2026-07-08"),
 ("harvey","Staff Software Engineer, Frontend","2026-06-24"),
 ("harvey","Senior Software Engineer, Frontend","2026-06-24"),
 ("ashby","Design Engineer - Americas","2026-06-12"),
 ("harvey","Senior Frontend Platform Engineer","2026-04-28"),
 ("ashby","Staff Design Engineer - Americas","2025-11-14"),
 ("harvey","Staff Software Engineer, Frontend","2025-08-22"),
 ("harvey","Senior Software Engineer, Frontend","2024-03-08")]
for path in sys.argv[1:]:
    d = json.load(open(path))
    jobs = [j for c in d["companies"] for j in c["jobs"]]
    ranked = sorted(jobs, key=lambda j: -j["score"])
    rank = {id(j): i + 1 for i, j in enumerate(ranked)}
    found, hidden30 = [], 0
    print(f"\n== {path}: {len(jobs)} roles kept (min_score {d['min_score']})")
    # Greenhouse often points absolute_url at the employer's own careers site, so count
    # aggregator links (The Muse) instead of matching ATS hosts.
    agg = sum("themuse.com" in (j["url"] or "") for j in jobs)
    print(f"   aggregator links (The Muse): {agg}/{len(jobs)} · employer links: {len(jobs)-agg}/{len(jobs)}")
    for slug, title, date in GT:
        m = [j for j in jobs if j["id"].split(":")[1] == slug and j["title"].strip() == title
             and (j.get("posted") or "")[:10] == date]
        if m:
            j = max(m, key=lambda x: x["score"]); found.append(j)
            old = (j.get("age_days") or 0) > 30; hidden30 += old
            print(f"   HIT  {slug:10s} {title[:44]:44s} score={j['score']:3d} rank={rank[id(j)]:4d} "
                  f"age={j.get('age_days')}d{'  (hidden by default Fresh<=30d filter)' if old else ''}")
        else:
            print(f"   MISS {slug:10s} {title[:44]:44s}")
    top15 = sum(rank[id(j)] <= 15 for j in found)
    print(f"   recall: {len(found)}/18 in run file · {len(found)-hidden30}/18 visible with default "
          f"30-day filter · {top15}/18 in top 15 by score")
