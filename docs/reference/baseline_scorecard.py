# BASELINE SCORECARD (2026-10-18). Encodes the web-search-only test the skill must beat.
# Data rows are hand-verified results from that run; fit scores are judgment from title+location.
# Keep the metric definitions; replace W with the skill's own output when running evals (HANDOFF.md §11).
# Web-search baseline: the 20 results an agent would plausibly hand back from 7 searches.
# status: verified against the employer's live ATS (Greenhouse/Ashby/Lever API) or the page itself.
# fit: judgment vs the test resume (2 strong, 1 partial, 0 mismatch). posted: earliest reliable date found.
W = [  # id, company, title, link_type, dup_of, status, posted, fit
 (1,"Vanta","Sr SWE, Design Systems","aggregator",None,"closed","?",2),
 (2,"Jobgether(repost)","SWE, Design Systems (CO remote)","aggregator",None,"closed","?",1),
 (3,"Jobgether(repost)","Sr SWE, Frontend","aggregator",None,"closed","?",2),
 (4,"Front","Senior Design Engineer","aggregator",None,"open","2026-10-06",2),
 (5,"Front","Senior Design Engineer","aggregator",4,"open","2026-10-06",2),
 (6,"Front","Senior Design Engineer","aggregator",4,"open","2026-10-06",2),
 (7,"(hidden)","Sr FE Eng, Design Systems","paywall",None,"unverifiable","?",2),
 (8,"Jobgether(repost)","Sr SWE, Frontend Platform","aggregator",None,"closed","?",2),
 (9,"Mercury","Sr FE Eng, Design Systems","aggregator",None,"closed","2026-07-10",2),
 (10,"Designbase","Sr Frontend Developer","aggregator",None,"unverifiable","?",1),
 (11,"Attention","Design Engineer","aggregator",None,"open","2025-08-08",1),
 (12,"Ashby","Design Engineer, Americas","aggregator",None,"open","2026-06-12",2),
 (13,"Ashby","Staff Design Engineer, Americas","aggregator",None,"open","2025-11-14",2),
 (14,"Greenhouse","Sr UX Design Eng, Design Systems (US)","aggregator",None,"closed","?",2),
 (15,"Greenhouse","Sr UX Design Eng, Design Systems (CA)","aggregator",None,"closed","?",0),
 (16,"xAI","Sr Frontend Eng, Grok","aggregator",None,"closed","?",1),
 (17,"(recruiter)","Sr FE Eng, React+AI","recruiter",None,"closed","2026-05-30",1),
 (18,"Freshworks","Frontend AI UI Engineer","aggregator",None,"closed","2025-08-20",1),
 (19,"(recruiter)","Sr SWE React/Next, WeHo hybrid","recruiter",None,"open","?",2),
 (20,"Givebutter","Design Engineer","aggregator",None,"closed","?",1),
]
CUTOFF = "2026-10-11"
uniq = [r for r in W if r[4] is None]
open_ = [r for r in uniq if r[5] == "open"]
fresh = [r for r in open_ if r[6] != "?" and r[6] >= CUTOFF]
good_any_age = [r for r in open_ if r[7] == 2]
print(f"results returned:                {len(W)}")
print(f"exact duplicates:                {len(W)-len(uniq)}")
print(f"links direct to employer ATS:    {sum(r[3]=='ats' for r in W)}/{len(W)}")
print(f"unique postings:                 {len(uniq)}")
for s in ("open","closed","unverifiable"):
    n = sum(r[5]==s for r in uniq); print(f"  {s:13s}                  {n:2d}  ({n/len(uniq):.0%})")
print(f"open AND posted in last 7 days:  {len(fresh)}")
print(f"open AND strong fit (any age):   {len(good_any_age)}  -> {[r[1] for r in good_any_age]}")
print(f"PASS criterion (open+fresh+fit): {sum(r[7]==2 for r in fresh)}/20")

# Ground truth: 49 employer boards probed directly. Strong-fit, open, US-remote/LA-eligible roles
# (title+location judgment; false positives like 'Data Center Design Engineer' removed by hand).
GT = [("Replit","Design Engineer","2026-10-16"),("ElevenLabs","Full-Stack (FE-leaning), Studio","2026-10-09"),
 ("OpenAI","Frontend SWE, ChatGPT","2026-10-08"),("Ramp","Design Systems Lead","2026-09-30"),
 ("Vapi","MTS, Frontend","2026-09-22"),("Ramp","SWE, Frontend, Growth","2026-09-21"),
 ("Vercel","Design Engineer","2026-09-15"),("Affirm","Sr SWE, Frontend (Auth)","2026-09-10"),
 ("Perplexity","MTS, Design System","2026-08-11"),("Harvey","Frontend Platform Eng","2026-07-31"),
 ("Ramp","Design Engineer","2026-07-08"),("Harvey","Staff SWE, Frontend","2026-06-24"),
 ("Harvey","Sr SWE, Frontend","2026-06-24"),("Ashby","Design Engineer, Americas","2026-06-12"),
 ("Harvey","Sr Frontend Platform Eng","2026-04-28"),("Ashby","Staff Design Engineer, Americas","2025-11-14"),
 ("Harvey","Staff SWE, Frontend","2025-08-22"),("Harvey","Sr SWE, Frontend","2024-03-08")]
found_by_search = {("Ashby","Design Engineer, Americas"),("Ashby","Staff Design Engineer, Americas")}
hit = [g for g in GT if (g[0],g[1]) in found_by_search]
print(f"\nGROUND TRUTH strong-fit open roles on 49 boards: {len(GT)}")
print(f"  of which web search surfaced:  {len(hit)}  (recall {len(hit)/len(GT):.0%})")
print(f"  posted in last 7 days:          {sum(g[2]>=CUTOFF for g in GT)}  -> {[g[0]+' '+g[1] for g in GT if g[2]>=CUTOFF]}")
print(f"  posted in last 30 days:         {sum(g[2]>='2026-09-18' for g in GT)}")
print(f"  older than 6 months, still open:{sum(g[2]<'2026-04-18' for g in GT)}")
