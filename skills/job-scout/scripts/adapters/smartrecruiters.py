"""SmartRecruiters adapter (api.smartrecruiters.com posting API). Field notes: references/ats-notes.md.

The list is paged (100 postings per page, newest first) and carries no description or pay;
the single-posting endpoint has both (`jobAd.sections`, `compensation`). An unknown company
answers 200 with no postings, so it reads as an empty (unverified) board, never a dead one.

What it does NOT do: no caching (probe.py) and no pay parsing from description text —
pay comes only from the detail endpoint's `compensation` field.
"""
import net
import normalize as norm  # the module; `normalize` below is this adapter's contract function

from adapters import _common

BASE = "https://api.smartrecruiters.com/v1/companies/%s/postings"
PAGE = 100  # the API's largest page; a bigger `limit` is silently clamped to 100
# shortcut: a board stops at MAX_PAGES pages (the newest 500 postings, 5 requests); raise it if a
# company you need posts more. probe.py marks a list this long as capped so it never closes roles.
MAX_PAGES = 5
MAX_JOBS = PAGE * MAX_PAGES
JOB_PAGE = "https://jobs.smartrecruiters.com/%s/%s"
_INTERVALS = {"YEARLY": "year", "MONTHLY": "month", "WEEKLY": "week", "DAILY": "day", "HOURLY": "hour"}


def fetch_board(slug, budget=None):
    """Raw postings, newest first, up to MAX_JOBS; [] for an empty or unknown company; None on 404/410."""
    out = []
    for page in range(MAX_PAGES):
        data = net.get_json(BASE % _common.quote_slug(slug) + "?limit=%d&offset=%d" % (PAGE, page * PAGE), budget)
        if data is None:
            if page:  # gone mid-paging: a partial list must not count as the whole board
                raise net.NetError("SmartRecruiters board %s answered 404/410 on page %d" % (slug, page + 1))
            return None
        content = data.get("content") or []
        out.extend(content)
        if len(content) < PAGE or len(out) >= (data.get("totalFound") or 0):
            break
    return out


def fetch_job(slug, job_id, budget=None):
    """Raw single posting with description and pay, or None when it has closed (404, or active false)."""
    raw = net.get_json(BASE % _common.quote_slug(slug) + "/%s" % job_id, budget)
    if raw is None or raw.get("active") is False:  # active:false not seen live; treated as closed to be safe
        return None
    return raw


def _location(loc):
    text = loc.get("fullLocation") or ", ".join(
        p for p in (loc.get("city"), loc.get("region"), (loc.get("country") or "").upper()) if p)
    parts = []
    for p in text.split(","):  # fullLocation leaves empty parts ("Staines, , United Kingdom")
        p = p.strip()
        if p and p not in parts:
            parts.append(p)
    return ", ".join(parts)


def _pay(raw):
    c = raw.get("compensation") or {}
    return _common.comp(c.get("min"), c.get("max"), c.get("currency"), _INTERVALS.get(c.get("period")))


def _description(raw):
    sections = ((raw.get("jobAd") or {}).get("sections") or {}).values()
    parts = []
    for s in sections:
        text = norm.html_to_text(s.get("text"))
        if text:
            parts.append(((s.get("title") or "").strip() + "\n\n" + text).strip())
    return "\n\n".join(parts) or None


def normalize(raw, slug, company):
    loc = raw.get("location") or {}
    text = _location(loc)
    hint = "remote" if loc.get("remote") else "hybrid" if loc.get("hybrid") else None
    identifier = (raw.get("company") or {}).get("identifier") or slug
    return _common.job(
        "smartrecruiters", slug, company, raw.get("id"), raw.get("name"),
        raw.get("postingUrl") or JOB_PAGE % (_common.quote_slug(identifier), raw.get("id")),
        [text] if text else [],
        remote_flag=True if loc.get("remote") else None, workplace_hint=hint,
        countries=_common.country_codes([loc.get("country")]),
        department=(raw.get("department") or {}).get("label"),
        first_published=_common.iso_date(raw.get("releasedDate")),
        pay=_pay(raw),
        description_text=_description(raw),
    )
