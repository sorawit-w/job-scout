"""ATS adapter port: the one contract every job-board adapter implements.

Each adapter module (greenhouse, ashby, lever) provides three functions:

    fetch_board(slug)                -> list of raw job dicts from the board's list endpoint
    normalize(raw, slug, company)    -> one normalized job dict (schema: references/ats-notes.md)
    fetch_job(slug, job_id)          -> raw job dict, or None when the job is gone (404 = closed)

probe.py is the composition point: it looks adapters up in REGISTRY by the `ats`
column of companies.csv. Adapters are registered in M1b.

What it does NOT do: no network, no caching, no normalization — only the contract.
"""

CONTRACT = ("fetch_board", "normalize", "fetch_job")

REGISTRY = {}


def missing(module):
    """Names from CONTRACT that `module` lacks or does not expose as callables."""
    return [name for name in CONTRACT if not callable(getattr(module, name, None))]
