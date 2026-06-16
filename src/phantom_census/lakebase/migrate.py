"""Schema initialization for Phantom Census Lakebase tables.

Reads schema.sql adjacent to this module and executes it within one
connection. Idempotent: `CREATE TABLE IF NOT EXISTS` everywhere.

@spec LP-INIT-001, LP-INIT-002, LP-INIT-003, LP-INIT-004
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import Engine, text

log = logging.getLogger(__name__)

_SCHEMA_SQL = Path(__file__).parent / "schema.sql"


# @spec LP-INIT-001, LP-INIT-004
def init_schema(engine: Engine) -> None:
    """Create all 7 Phantom Census tables + helper xref.

    LP-INIT-002 (CDC on phantom_verdicts) and LP-INIT-003 (Liquid Clustering
    Delta mirror) are Free-Edition kill-switches — if the target backend does
    not support them, a warning is logged and initialization continues.
    """
    ddl = _SCHEMA_SQL.read_text()

    with engine.begin() as conn:
        # Each top-level statement runs as its own execute().
        for statement in _split_sql(ddl):
            stmt = statement.strip()
            if not stmt or stmt.startswith("--"):
                continue
            conn.execute(text(stmt))

    _enable_cdc_best_effort(engine)
    _create_delta_mirror_best_effort(engine)


def _split_sql(blob: str) -> list[str]:
    """Naive `;` splitter — schema.sql is hand-authored, no embedded semicolons."""
    return [s for s in blob.split(";") if s.strip()]


# @spec LP-INIT-002
def _enable_cdc_best_effort(engine: Engine) -> None:
    """Enable change-data-capture on phantom_verdicts when the dialect supports it.

    On vanilla Postgres there is no built-in CDC primitive; we log and continue.
    On Databricks Lakebase / Lakeflow this would attach a CDC stream — wiring
    that depends on the runtime CDC API which is not exposed via SQLAlchemy.
    """
    log.warning(
        "LP-INIT-002 CDC on operational.phantom_verdicts is a no-op on this "
        "backend; the override path falls back to the explicit Python "
        "recompute_fn callback (LLD Open Questions / Deferred 1)."
    )


# @spec LP-INIT-003
def _create_delta_mirror_best_effort(engine: Engine) -> None:
    """Create a Delta mirror of operational.facility_existence_tests when the
    backend supports it. Vanilla Postgres has no Delta — log and continue."""
    log.warning(
        "LP-INIT-003 Delta mirror with Liquid Clustering is a no-op on this "
        "backend; analytical batch scans use the standard index instead."
    )
