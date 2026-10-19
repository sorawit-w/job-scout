"""ATS adapter port: the one contract every job-board adapter implements.

Each adapter module (greenhouse, ashby, lever, smartrecruiters) provides three functions:

    fetch_board(slug)                -> list of raw job dicts from the board's list endpoint
    normalize(raw, slug, company)    -> one normalized job dict (schema: references/ats-notes.md)
    fetch_job(slug, job_id)          -> raw job dict, or None when the job is gone (404 = closed)

probe.py is the composition point: it looks adapters up in REGISTRY by the `ats`
column of companies.csv. fetch_board and fetch_job also take an optional
`budget` (net.Budget). fetch_board returns [] for an empty board and None when
the board is gone (404), so callers can tell an unverified board from a dead one.

What it does NOT do: no network, no caching, no normalization — only the contract.
"""

CONTRACT = ("fetch_board", "normalize", "fetch_job")


def missing(module):
    """Names from CONTRACT that `module` lacks or does not expose as callables."""
    return [name for name in CONTRACT if not callable(getattr(module, name, None))]


from adapters import ashby, greenhouse, lever, smartrecruiters  # noqa: E402  (after missing(): adapters import this package)

REGISTRY = {"greenhouse": greenhouse, "ashby": ashby, "lever": lever, "smartrecruiters": smartrecruiters}
