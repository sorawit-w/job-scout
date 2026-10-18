import urllib.request
for u in ["https://boards-api.greenhouse.io/v1/boards/vercel/jobs",
          "https://api.ashbyhq.com/posting-api/job-board/linear",
          "https://api.lever.co/v0/postings/jobgether?mode=json&limit=1"]:
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent":"job-scout-m0"}), timeout=15) as r:
            print("OK  ", r.status, u.split("/")[2])
    except Exception as e:
        print("FAIL", type(e).__name__, str(e)[:60], u.split("/")[2])
