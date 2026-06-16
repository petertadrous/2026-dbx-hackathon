"""SQLAlchemy connection management for Lakebase.

The Lakebase URL is read from the `LAKEBASE_URL` environment variable when
not passed explicitly. Tests typically inject their own URL via
`get_engine(url=test_dsn)`.
"""
from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine


def get_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    """Return a SQLAlchemy Engine bound to Lakebase (or a test Postgres).

    Order of resolution: explicit ``url`` arg → ``LAKEBASE_URL`` env → error.
    """
    resolved = url or os.environ.get("LAKEBASE_URL")
    if not resolved:
        raise RuntimeError(
            "No Lakebase URL provided. Set LAKEBASE_URL or pass url= explicitly."
        )
    return create_engine(resolved, future=True, echo=echo)
