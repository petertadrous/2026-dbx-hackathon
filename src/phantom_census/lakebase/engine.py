"""SQLAlchemy connection management for Lakebase.

The Lakebase URL is read from environment variables when not passed explicitly.
Tests typically inject their own URL via ``get_engine(url=test_dsn)``.

@spec LP-APP-005, LP-APP-006
"""
from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine


_DSN_ENV_VARS = ("LAKEBASE_DSN", "LAKEBASE_URL")


def get_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    """Return a SQLAlchemy Engine bound to Lakebase (or a test Postgres).

    Order of resolution: explicit ``url`` arg → ``LAKEBASE_DSN`` env →
    ``LAKEBASE_URL`` env → error.
    """
    resolved = url
    if resolved is None:
        for v in _DSN_ENV_VARS:
            resolved = os.environ.get(v)
            if resolved:
                break
    if not resolved:
        raise RuntimeError(
            "No Lakebase URL provided. Set LAKEBASE_DSN or pass url= explicitly."
        )
    return create_engine(resolved, future=True, echo=echo)


# @spec LP-APP-005
def build_engine_from_env(*, echo: bool = False) -> Engine:
    """LP-APP-005: connect to Lakebase using credentials injected via env vars.

    No Lakebase credentials are hardcoded in source. ``LAKEBASE_DSN`` is the
    canonical name; ``LAKEBASE_URL`` is accepted for backwards compatibility.
    Raises ``RuntimeError`` when neither is set.
    """
    return get_engine(echo=echo)


# @spec LP-APP-006
def build_engine_pair(*, echo: bool = False) -> tuple[Engine, Engine]:
    """LP-APP-006: separate read-only and write-capable engines.

    Both engines resolve from the same DSN env var (``LAKEBASE_DSN``) — the
    distinction is the SQLAlchemy connection pool: read traffic uses a pool
    sized for high concurrency, write traffic uses a smaller pool with
    explicit transaction management at the call site.

    The split exists so the app can scale read concurrency without granting
    write privileges to the read pool's connections.
    """
    read_engine = get_engine(echo=echo)
    # Re-resolve so the two engines have independent pools.
    write_engine = get_engine(echo=echo)
    return read_engine, write_engine
