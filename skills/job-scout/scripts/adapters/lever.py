"""Lever adapter (api.lever.co postings API). Field notes: references/ats-notes.md.

What it does NOT do: no caching (probe.py), no EU host (no seed board needs it — see
ats-notes), and no pay parsing from description text — pay comes only from `salaryRange`.
"""
import net
import normalize as norm  # the module; `normalize` below is this adapter's contract function

from adapters import _common

BASE = "https://api.lever.co/v0/postings/%s"
_INTERVALS = {"per-year-salary": "year", "per-month-salary": "month", "per-week-salary": "week",
              "per-day-wage": "day", "per-hour-wage": "hour"}


def fetch_board(slug, budget=None):
    """Raw postings; [] for an empty board; None when the board is gone (404)."""
    data = net.get_json(BASE % _common.quote_slug(slug) + "?mode=json", budget)
    if data is None:
        return None
    return data if isinstance(data, list) else []


def fetch_job(slug, job_id, budget=None):
    """Raw single posting, or None when it has closed (404)."""
    return net.get_json(BASE % _common.quote_slug(slug) + "/%s?mode=json" % job_id, budget)


def _pay(raw):
    r = raw.get("salaryRange") or {}
    return _common.comp(r.get("min"), r.get("max"), r.get("currency"), _INTERVALS.get(r.get("interval")))


def _description(raw):
    parts = [raw.get("descriptionPlain") or norm.html_to_text(raw.get("description"))]
    for block in raw.get("lists") or []:
        parts.append((block.get("text") or "").strip())
        parts.append(norm.html_to_text(block.get("content")))
    parts.append(raw.get("additionalPlain") or "")
    return "\n\n".join(p for p in parts if p) or None


def normalize(raw, slug, company):
    cats = raw.get("categories") or {}
    locations = []
    for loc in [cats.get("location")] + list(cats.get("allLocations") or []):
        if loc and loc not in locations:
            locations.append(loc)
    workplace = raw.get("workplaceType")
    return _common.job(
        "lever", slug, company, raw.get("id"), raw.get("text"), raw.get("hostedUrl") or raw.get("applyUrl"), locations,
        remote_flag=True if workplace == "remote" else None, workplace_hint=workplace,
        countries=_common.country_codes([raw.get("country")]),
        department=cats.get("department") or cats.get("team"),
        first_published=_common.iso_date(raw.get("createdAt")),
        pay=_pay(raw),
        description_text=_description(raw),
    )
