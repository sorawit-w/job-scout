"""USAJOBS adapter (data.usajobs.gov). Field notes: references/ats-notes.md.

USAJOBS is one opt-in, cross-agency keyword search, not a per-company board: the slug is
always "all" and the company is the hiring agency. Search needs a free key that each user
requests for themselves (keys may not be shared, so job-scout never ships one). The key and
the registered email are read only from JOB_SCOUT_USAJOBS_KEY / JOB_SCOUT_USAJOBS_EMAIL and
sent only as request headers — never put in a URL, logged, or stored (net.py never records
request headers in fixtures). Without both, fetch_board returns None and makes no request;
the caller says "USAJOBS skipped: no key" once.

fetch_job uses the keyless Historic JOA endpoint. Its live check means "still accepting
applications per USAJOBS": status "Accepting applications" and a close date not yet passed.

What it does NOT do: no caching (probe.py), no pay parsing from text — pay comes only from
PositionRemuneration (search) or minimumSalary/maximumSalary (JOA). A JOA record carries no
description, so normalize(fetch_job(...)) has description_text None.
"""
import datetime
import os
import urllib.parse

import net
import normalize as norm  # the module; `normalize` below is this adapter's contract function

from adapters import _common

KEY_ENV = "JOB_SCOUT_USAJOBS_KEY"
EMAIL_ENV = "JOB_SCOUT_USAJOBS_EMAIL"
SEARCH = "https://data.usajobs.gov/api/Search"
JOA = "https://data.usajobs.gov/api/historicjoa?USAJOBSControlNumbers=%s"
JOB_PAGE = "https://www.usajobs.gov/job/%s"
MAX_TERMS = 3  # one search per term; extra terms mostly re-find the same postings
# shortcut: newest MAX_PAGES * PAGE postings per term (2 requests); raise MAX_PAGES if a term needs more.
MAX_PAGES = 2
PAGE = 100  # the API allows up to 500; 100 keeps each response and replay fixture small
OPEN = "Accepting applications"
# Official RemunerationRateIntervalCode list (data.usajobs.gov/api/codelist, 2026-10-19). PW is
# "Piece Work", not weekly; BW, FB, ST, SY, WC have no schema interval.
_INTERVALS = {"PA": "year", "PM": "month", "PD": "day", "PH": "hour"}
_JOA_INTERVALS = {"Per Year": "year", "Per Month": "month", "Per Day": "day", "Per Hour": "hour"}


def enabled():
    """True only when both the key and the registered email are set in the environment."""
    return bool(os.environ.get(KEY_ENV, "").strip() and os.environ.get(EMAIL_ENV, "").strip())


def _today():  # test seam
    return datetime.date.today()


def _search_url(term, page, location=None):
    params = [("Keyword", term), ("ResultsPerPage", PAGE), ("Page", page),
              ("SortField", "opendate"), ("SortDirection", "Desc")]
    if location:
        params.append(("LocationName", location))
    return SEARCH + "?" + urllib.parse.urlencode(params)


def fetch_board(slug="all", budget=None, terms=None, location=None):
    """Raw search items for up to MAX_TERMS keywords, de-duplicated by control number.
    None when no key is set (no request made); [] when there are no terms."""
    if not enabled():
        return None
    headers = {"Host": "data.usajobs.gov", "User-Agent": os.environ[EMAIL_ENV].strip(),
               "Authorization-Key": os.environ[KEY_ENV].strip()}
    out, seen = [], set()
    for term in [t.strip() for t in terms or [] if t and t.strip()][:MAX_TERMS]:
        for page in range(1, MAX_PAGES + 1):
            data = net.get_json(_search_url(term, page, location), budget, headers=headers)
            result = (data or {}).get("SearchResult") or {}
            items = result.get("SearchResultItems") or []
            for item in items:
                cid = str(item.get("MatchedObjectId") or "")
                if cid and cid not in seen:
                    seen.add(cid)
                    out.append(item)
            try:
                pages = int((result.get("UserArea") or {}).get("NumberOfPages") or 0)
            except (TypeError, ValueError):
                pages = 0
            if not items or page >= pages:
                break
    return out


def fetch_job(slug, job_id, budget=None):
    """Historic JOA record while it is still accepting applications; None when closed,
    cancelled, past its close date, or unknown. Network errors raise."""
    data = net.get_json(JOA % urllib.parse.quote(str(job_id), safe=""), budget)  # unknown number: 204 → {}
    row = next((r for r in (data or {}).get("data") or [] if str(r.get("usajobsControlNumber")) == str(job_id)), None)
    if row is None or row.get("positionOpeningStatus") != OPEN:
        return None
    today = _today().isoformat()
    for close in (row.get("positionCloseDate"), row.get("positionExpireDate")):  # expire = early close, when set
        if close and str(close)[:10] < today:
            return None
    return row


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _flag(value):
    """USAJOBS booleans: true/false in Search (per client models), "Y"/"N" in JOA. None when absent."""
    text = str(value).strip().lower()
    return True if text in ("true", "y", "yes") else False if text in ("false", "n", "no") else None


def _text(value):
    if isinstance(value, list):
        return "\n\n".join(t for t in (norm.html_to_text(v) for v in value) if t)
    return norm.html_to_text(value)


def _from_joa(raw, slug, company):
    cid = raw.get("usajobsControlNumber")
    locations = [", ".join(p for p in (loc.get("positionLocationCity"), loc.get("positionLocationState")) if p)
                 for loc in raw.get("positionlocations") or []]
    countries = [loc.get("positionLocationCountry") for loc in raw.get("positionlocations") or []]
    telework = _flag(raw.get("teleworkEligible"))
    return _common.job(
        "usajobs", slug, raw.get("hiringAgencyName") or company, cid, raw.get("positionTitle"), JOB_PAGE % cid,
        [loc for loc in locations if loc], workplace_hint="hybrid" if telework else None,
        countries=_common.country_codes(countries), department=raw.get("hiringDepartmentName"),
        first_published=_common.iso_date(raw.get("positionOpenDate")),
        pay=_common.comp(_number(raw.get("minimumSalary")), _number(raw.get("maximumSalary")), "USD",
                         _JOA_INTERVALS.get(raw.get("salaryType"))),
    )


def normalize(raw, slug, company):
    """One job from a Search item, or from the Historic JOA record fetch_job returns."""
    if "usajobsControlNumber" in raw:
        return _from_joa(raw, slug, company)
    d = raw.get("MatchedObjectDescriptor") or {}
    details = (d.get("UserArea") or {}).get("Details") or {}
    places = d.get("PositionLocation") or []
    locations = [p.get("LocationName") for p in places if p.get("LocationName")] or (
        [d["PositionLocationDisplay"]] if d.get("PositionLocationDisplay") else [])
    remote, telework = _flag(details.get("RemoteIndicator")), _flag(details.get("TeleworkEligible"))
    # Both flags explicitly false = report on site; absent flags say nothing.
    hint = "remote" if remote else "hybrid" if telework else "onsite" if (remote, telework) == (False, False) else None
    pay = (d.get("PositionRemuneration") or [{}])[0]
    url = (d.get("PositionURI") or JOB_PAGE % raw.get("MatchedObjectId")).replace(":443/", "/", 1)
    description = "\n\n".join(t for t in (_text(details.get("JobSummary")), _text(details.get("MajorDuties")),
                                          _text(d.get("QualificationSummary"))) if t)
    return _common.job(
        "usajobs", slug, d.get("OrganizationName") or company, raw.get("MatchedObjectId"), d.get("PositionTitle"),
        url, locations, remote_flag=remote, workplace_hint=hint,
        countries=_common.country_codes([p.get("CountryCode") for p in places]),
        department=d.get("DepartmentName"),
        first_published=_common.iso_date(d.get("PublicationStartDate")),
        pay=_common.comp(_number(pay.get("MinimumRange")), _number(pay.get("MaximumRange")), "USD",
                         _INTERVALS.get(pay.get("RateIntervalCode"))),
        description_text=description or None,
    )
