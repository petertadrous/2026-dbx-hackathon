"""SQLAlchemy connection management for Lakebase.

Two paths:

1. Static-URL path (`LAKEBASE_DSN` env var) — used for local Postgres,
   testcontainers, and any CI runner that already has a Postgres DSN string.
2. Lakebase-resource path — used when the app is deployed on Databricks
   Apps with a `postgres` resource declared in the bundle. The platform
   injects `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `LAKEBASE_ENDPOINT`;
   the app fetches a fresh OAuth token via the Databricks SDK and refreshes
   it on every new physical connection.

@spec LP-APP-005, LP-APP-006
"""
from __future__ import annotations

import os
import threading
import time

from sqlalchemy import Engine, create_engine, event


_DSN_ENV_VARS = ("LAKEBASE_DSN", "LAKEBASE_URL")
_TOKEN_REFRESH_SECONDS = 30 * 60  # refresh well before the 1-hour expiry


def _has_lakebase_resource_env() -> bool:
    return bool(os.environ.get("LAKEBASE_ENDPOINT")) and bool(
        os.environ.get("PGHOST")
    )


def get_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    """Return a SQLAlchemy Engine bound to Lakebase (or a test Postgres).

    Resolution order:
      1. Explicit ``url`` arg
      2. ``LAKEBASE_DSN`` / ``LAKEBASE_URL`` env (static DSN)
      3. Databricks Apps `postgres` resource env (`LAKEBASE_ENDPOINT` +
         `PGHOST` + `PGUSER` + `PGDATABASE`) — uses OAuth token refresh.
      4. RuntimeError.
    """
    if url is not None:
        return create_engine(url, future=True, echo=echo)

    for v in _DSN_ENV_VARS:
        env_url = os.environ.get(v)
        if env_url:
            return create_engine(env_url, future=True, echo=echo)

    if _has_lakebase_resource_env():
        return _build_engine_from_lakebase_resource(echo=echo)

    raise RuntimeError(
        "No Lakebase URL provided. Set LAKEBASE_DSN, pass url= explicitly, "
        "or deploy with a Databricks Apps `postgres` resource."
    )


# @spec LP-APP-005
def build_engine_from_env(*, echo: bool = False) -> Engine:
    """LP-APP-005: connect to Lakebase using credentials injected via env vars."""
    return get_engine(echo=echo)


# @spec LP-APP-006
def build_engine_pair(*, echo: bool = False) -> tuple[Engine, Engine]:
    """LP-APP-006: separate read-only and write-capable engines."""
    return get_engine(echo=echo), get_engine(echo=echo)


# ─── Lakebase-resource path ───────────────────────────────────────────────


def _build_engine_from_lakebase_resource(*, echo: bool) -> Engine:
    """Build a SQLAlchemy engine that uses an OAuth-token credential which is
    refreshed by a background thread.

    The Databricks Apps platform injects the `postgres` resource as a set of
    env vars (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `LAKEBASE_ENDPOINT`).
    The token is fetched on demand via `w.postgres.generate_database_credential`
    and stored in a mutable container; the SQLAlchemy `do_connect` event hook
    injects the current token as the password for every new physical
    connection.
    """
    host = os.environ["PGHOST"]
    port = int(os.environ.get("PGPORT", "5432"))
    database = os.environ["PGDATABASE"]
    user = os.environ["PGUSER"]
    endpoint = os.environ["LAKEBASE_ENDPOINT"]

    token_holder = _TokenHolder(endpoint=endpoint)
    token_holder.refresh()  # raise early if creds aren't usable

    # Password is set by the do_connect event hook; the URL's password slot
    # is a placeholder that gets overwritten before each connect.
    url = (
        f"postgresql+psycopg://{user}:placeholder@{host}:{port}/{database}"
        f"?sslmode=require"
    )

    engine = create_engine(
        url,
        future=True,
        echo=echo,
        pool_pre_ping=True,
        pool_recycle=_TOKEN_REFRESH_SECONDS,
    )

    @event.listens_for(engine, "do_connect")
    def _inject_token(_dialect, _conn_rec, _cargs, cparams):
        cparams["password"] = token_holder.current()

    token_holder.start_background_refresh()
    return engine


class _TokenHolder:
    """Lazy + background-refreshed OAuth token for a Lakebase endpoint."""

    def __init__(self, *, endpoint: str) -> None:
        self._endpoint = endpoint
        self._lock = threading.Lock()
        self._token: str | None = None
        self._thread: threading.Thread | None = None

    def refresh(self) -> None:
        """Fetch a fresh token from the workspace and store it."""
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient()
        cred = w.postgres.generate_database_credential(endpoint=self._endpoint)
        with self._lock:
            self._token = cred.token

    def current(self) -> str:
        with self._lock:
            if self._token is None:
                pass  # refresh outside the lock
            else:
                return self._token
        self.refresh()
        with self._lock:
            assert self._token is not None
            return self._token

    def start_background_refresh(self) -> None:
        """Spawn a daemon thread that re-mints the token every 30 min."""
        if self._thread is not None and self._thread.is_alive():
            return

        def _loop() -> None:
            while True:
                time.sleep(_TOKEN_REFRESH_SECONDS)
                try:
                    self.refresh()
                except Exception:  # noqa: BLE001
                    # Next refresh tick will retry; the do_connect hook still
                    # has the previous token, which is valid for up to 1 hour.
                    pass

        t = threading.Thread(target=_loop, name="lakebase-token-refresh",
                             daemon=True)
        t.start()
        self._thread = t
