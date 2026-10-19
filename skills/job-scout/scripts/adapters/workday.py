"""Workday adapter (<tenant>.<wdN>.myworkdayjobs.com public "CXS" JSON). Field notes: references/ats-notes.md.

Board slug: "<tenant>.<wdN>.<site>" — dots, because a job key is "ats:slug:job_id" and the slug may
not hold ":". The slug becomes part of a URL, so anything else raises ValueError.

The list is a keyword search (POST, 20 postings a page), never the whole board, so a board list is
always partial: a job missing from it is unseen, not closed.

Job id rule: the posting's `jobPostingId` — the last part of `externalPath`
("/job/San-Diego-CA/Clinical-Nurse-RN-…_JR209985-1" → "Clinical-Nurse-RN-…_JR209985-1"). The
detail endpoint finds a posting by that whole part; the requisition id alone ("JR209985-1") and
a changed title part both 404, while the location part is ignored (all checked 2026-10-19). So
the id alone rebuilds the detail URL (`…/job/<id>`), and the detail response carries the same
value as `jobPostingInfo.jobPostingId`.

What it does NOT do: no caching (probe.py), no facets, no whole-board crawl, and no pay — Workday
has no pay field, and scripts never parse pay from description text.
"""
import re
import urllib.parse

import net
import normalize as norm  # the module; `normalize` below is this adapter's contract function

from adapters import _common

_SLUG_RE = re.compile(r"([a-z0-9-]+)\.(wd[0-9]+)\.([A-Za-z0-9_-]+)")
_COUNT_ONLY_RE = re.compile(r"\d+ Locations?", re.I)  # list text for a multi-location posting
PARTIAL = True  # the board list is a keyword search: probe.py never lets it close roles
# Search rows carry no work mode (and "3 Locations" rows no place); the detail record (fetch_job)
# has remoteType and every location. filter.py keeps such rows, and fetch_jd.py re-filters them.
MODE_ON_DETAIL = True
LIMIT = 20  # the largest page the API accepts: limit 21 answers HTTP 400 (checked 2026-10-19)
MAX_TERMS = 3  # each term costs up to MAX_PAGES requests per board; the brief's first terms are its best
# shortcut: a search stops after MAX_PAGES pages (60 postings per term);
# raise it if relevant roles sit deeper on big boards.
MAX_PAGES = 3


def _parts(slug):
    m = _SLUG_RE.fullmatch(slug or "")
    if not m:
        raise ValueError("bad Workday board slug %r (want <tenant>.<wdN>.<site>)" % (slug,))
    return m.groups()


def site_url(slug):
    """The board's CXS API root, e.g. https://sharp.wd1.myworkdayjobs.com/wday/cxs/sharp/External."""
    tenant, host, site = _parts(slug)
    return "https://%s.%s.myworkdayjobs.com/wday/cxs/%s/%s" % (tenant, host, tenant, site)


def _page_url(slug):
    tenant, host, site = _parts(slug)
    return "https://%s.%s.myworkdayjobs.com/%s" % (tenant, host, site)


def _post_json(url, payload, budget=None):
    """One search POST through net.get_json; a JSON object back, or None when the board is gone.
    Workday answers 422 for an unknown tenant or a board that moved to another wdN host, and 404
    for an unknown site (checked 2026-10-19); net.py maps only 404/410 to None, so 422 is mapped here."""
    try:
        data = net.get_json(url, budget, body=payload)
    except net.HTTPStatusError as e:
        if e.status == 422:
            return None
        raise
    if data is not None and not isinstance(data, dict):
        raise net.NetError("not a JSON object from %s" % url)
    return data


def fetch_board(slug, budget=None, terms=None):
    """Raw postings matching up to MAX_TERMS search terms, de-duplicated by externalPath; [] for no
    match; None when the board is gone. terms=None (or all blank): one blank search, first page only."""
    url = site_url(slug) + "/jobs"
    terms = [t.strip() for t in terms or [] if t and t.strip()][:MAX_TERMS]
    searches = [(t, MAX_PAGES) for t in terms] or [("", 1)]
    out, seen = [], set()
    for term, pages in searches:
        total = 0
        for page in range(pages):
            data = _post_json(url, {"appliedFacets": {}, "limit": LIMIT, "offset": page * LIMIT,
                                    "searchText": term}, budget)
            if data is None:
                return None
            postings = data.get("jobPostings")
            if not isinstance(postings, list):
                raise net.NetError("no jobPostings in Workday search from %s" % url)
            for p in postings:
                path = p.get("externalPath") if isinstance(p, dict) else None
                if path not in seen:
                    seen.add(path)
                    out.append(p)
            if page == 0 and isinstance(data.get("total"), int):
                total = data["total"]  # only page 1's total is reliable; past the end Workday repeats page 1
            if len(postings) < LIMIT or (page + 1) * LIMIT >= total:
                break
    return out


def fetch_job(slug, job_id, budget=None):
    """Raw detail response ({jobPostingInfo, …}), or None when the posting has closed (404/410).
    Any other failure raises net.NetError (unverified): a 422 means the board moved hosts, so the
    posting may still be open there."""
    if not job_id or job_id in (".", ".."):
        raise ValueError("bad Workday job id %r" % (job_id,))
    data = net.get_json(site_url(slug) + "/job/" + urllib.parse.quote(job_id, safe=""), budget)
    if data is not None and not (isinstance(data, dict) and isinstance(data.get("jobPostingInfo"), dict)):
        raise net.NetError("no jobPostingInfo in Workday job %s" % job_id)
    return data


def normalize(raw, slug, company):
    """One search posting or one detail response -> the normalized job."""
    page = _page_url(slug)
    info = raw.get("jobPostingInfo")
    if isinstance(info, dict):  # detail (fetch_job)
        job_id = info.get("jobPostingId")
        locations = [info.get("location")] + list(info.get("additionalLocations") or [])
        country = info.get("country") or {}
        countries = _common.country_codes([
            ((info.get("jobRequisitionLocation") or {}).get("country") or {}).get("alpha2Code"),
            country.get("alpha2Code") or country.get("descriptor")])
        url = info.get("externalUrl") or ""
        if not url.startswith(page.rsplit("/", 1)[0] + "/"):  # only ever the employer's own careers page
            url = "%s/job/%s" % (page, urllib.parse.quote(job_id or "", safe=""))
        title, workplace_hint = info.get("title"), info.get("remoteType")
        first_published = _common.iso_date(info.get("startDate"))
        description = norm.html_to_text(info.get("jobDescription")) or None
    else:  # search posting (fetch_board): postedOn is text, so no date; no description yet
        path = raw.get("externalPath") or ""
        job_id = urllib.parse.unquote(path.rsplit("/", 1)[-1]) if path.startswith("/job/") else None
        text = (raw.get("locationsText") or "").strip()
        locations = [] if _COUNT_ONLY_RE.fullmatch(text) else [text]
        countries, url = [], page + path
        title, workplace_hint, first_published, description = raw.get("title"), None, None, None
    if not job_id:
        raise ValueError("Workday posting has no jobPostingId / externalPath")
    return _common.job(
        "workday", slug, company, job_id, title, url, [loc for loc in locations if loc],
        workplace_hint=workplace_hint, countries=countries,
        first_published=first_published, description_text=description,
    )
