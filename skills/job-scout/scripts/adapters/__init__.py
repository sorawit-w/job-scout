"""ATS adapter port: the one contract every job-board adapter implements.

Each adapter module (greenhouse, ashby, lever, smartrecruiters, workday, usajobs) provides three functions:

    fetch_board(slug)                -> list of raw job dicts from the board's list endpoint
    normalize(raw, slug, company)    -> one normalized job dict (schema: references/ats-notes.md)
    fetch_job(slug, job_id)          -> raw job dict, or None when the job is gone (404 = closed)

probe.py is the composition point: it looks adapters up in REGISTRY by the `ats`
column of companies.csv. fetch_board and fetch_job also take an optional
`budget` (net.Budget). fetch_board returns [] for an empty board and None when
the board is gone (404), so callers can tell an unverified board from a dead one.

Search sources set `PARTIAL = True` (read it with getattr(module, "PARTIAL", False)): their
board list is a keyword search, never the whole board (workday, usajobs). Such a module also
  * takes `fetch_board(slug, budget, terms=[...])` — probe.py passes the brief's target_roles,
    then title_synonyms, cut to the module's MAX_TERMS;
  * sets MAX_TERMS and MAX_PAGES, so one board costs at most MAX_TERMS * MAX_PAGES requests
    (probe.py sizes its request budget from them);
  * never closes a saved role: a job missing from a search is unseen, not gone, so probe.py
    records the board under "partial_boards", never "live_boards", and does not cache it
    (the result depends on the terms).
A module whose fetch_job record cannot express some fields its board list has may name them in
`JOB_LACKS`; fetch_jd.py then keeps the candidate row's values for them (usajobs: remote).
A non-search module that pages through its board list sets MAX_PAGES too (smartrecruiters).
An opt-in source may also define `enabled()`; while it returns False probe.py makes no request
to it and records "<name>: no key" once under "skipped".

What it does NOT do: no network, no caching, no normalization — only the contract.
"""

CONTRACT = ("fetch_board", "normalize", "fetch_job")


def missing(module):
    """Names from CONTRACT that `module` lacks or does not expose as callables."""
    return [name for name in CONTRACT if not callable(getattr(module, name, None))]


from adapters import ashby, greenhouse, lever, smartrecruiters, usajobs, workday  # noqa: E402  (after missing(): adapters import this package)

REGISTRY = {"greenhouse": greenhouse, "ashby": ashby, "lever": lever, "smartrecruiters": smartrecruiters,
            "workday": workday, "usajobs": usajobs}
