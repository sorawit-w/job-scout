# M0 CONNECTOR SCORECARD (2026-10-18). Same metrics as baseline_scorecard.py, run against the
# Indeed, Dice and ZipRecruiter Claude connectors. Searches: "design engineer frontend",
# "senior frontend engineer", "design systems engineer" (remote US) + "staff frontend engineer"
# (Los Angeles). Fit is title-only judgment (same caveat as the baseline). Open status was NOT
# re-verified for connector rows; only the 18 ground-truth roles were re-checked on the employer ATS.
C = {  # returned, exact_dups, direct_ats_links, strong_fit_by_title, gt_hits_organic, gt_hits_named (of 3)
  "Indeed":       dict(returned=30, dups=4, direct=0, strong=2,  gt=0, named=0),
  "Dice":         dict(returned=40, dups=7, direct=0, strong=10, gt=1, named=0),
  "ZipRecruiter": dict(returned=20, dups=0, direct=0, strong=4,  gt=0, named=3),
}
GT_TOTAL = 18   # all 18 still open on the employer ATS on 2026-10-18 (re-checked)
# ZipRecruiter data errors found on the 3 named ground-truth roles, vs the employer ATS:
ZIP_ERRORS = [
  ("Vercel Design Engineer", "pay",  "$69,600-$100,800", "$208,000-$312,000"),
  ("Vercel Design Engineer", "date", "2 days ago",       "first published 2026-09-15"),
  ("Harvey Sr SWE, Frontend", "date", "27 days ago",      "first published 2024-03-08"),
  ("Harvey Sr SWE, Frontend", "mode", "On-site",          "San Francisco, remote allowed"),
]
OUTSIDE_SEED = ["ClickUp","Thumbtack","Grafana","Hims & Hers","Sift","Keeper","1Password","Circles","Chamberlain","Ravenna"]
print(f"{'connector':13s} returned  dups  direct-ATS  strong-fit  GT recall (search)  GT found by name")
for k, v in C.items():
    print(f"{k:13s} {v['returned']:8d}  {v['dups']:4d}  {v['direct']:4d}/{v['returned']:<5d} {v['strong']:6d}"
          f"      {v['gt']:2d}/{GT_TOTAL} ({v['gt']/GT_TOTAL:.0%})          {v['named']}/3")
print(f"\nWeb-search baseline (2026-10-18): direct-ATS 0/20, GT recall 2/18 (11%)")
print(f"\nZipRecruiter field errors on named GT roles: {len(ZIP_ERRORS)} across 2 of 3 roles")
for r in ZIP_ERRORS: print(f"  {r[0]:24s} {r[1]:5s} shown: {r[2]:18s} employer: {r[3]}")
print(f"\nStrong-fit employers found by connectors but missing from the 49-board seed: {len(OUTSIDE_SEED)}")
print("  " + ", ".join(OUTSIDE_SEED))
