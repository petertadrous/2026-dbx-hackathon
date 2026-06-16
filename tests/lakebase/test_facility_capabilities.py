"""Tests for the operational.facility_capabilities cascade table (DS-Q2).

The engine writer populates this table from EngineOutputs.facility_capabilities
so the desert-scoring recompute callback can iterate over a facility's
claimed capabilities per DS-MULTICAP-001.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import inspect, text


# @spec LP-INIT-001
def test_facility_capabilities_table_exists_with_composite_pk(engine):
    insp = inspect(engine)
    assert "facility_capabilities" in insp.get_table_names(schema="operational")
    pk = insp.get_pk_constraint("facility_capabilities", schema="operational")
    assert set(pk["constrained_columns"]) == {"facility_id", "capability"}


# @spec LP-EE-001
def test_engine_writer_populates_facility_capabilities(
    engine, sample_engine_outputs,
):
    """The LP writer reads outputs.facility_capabilities (a new field on
    EngineOutputs) and writes one row per (facility_id, capability)."""
    sample_engine_outputs.facility_capabilities = {
        "F1": ["maternity"],
        "F2": ["maternity", "icu"],
    }
    from phantom_census.lakebase.writer import load_engine_outputs
    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT facility_id, capability "
            "FROM operational.facility_capabilities "
            "ORDER BY facility_id, capability"
        )).fetchall()
    pairs = {(r.facility_id, r.capability) for r in rows}
    assert pairs == {
        ("F1", "maternity"),
        ("F2", "icu"), ("F2", "maternity"),
    }


# @spec LP-EE-001
def test_engine_writer_replaces_facility_capabilities_on_rerun(
    engine, sample_engine_outputs,
):
    """A re-batch where a facility's capability set has changed should mirror
    the new set — old (facility_id, capability) rows that no longer apply must
    be removed so the recompute callback never sees stale capability rows."""
    sample_engine_outputs.facility_capabilities = {
        "F2": ["maternity", "icu"],
    }
    from phantom_census.lakebase.writer import load_engine_outputs
    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))

    # Re-batch with F2 dropping icu.
    sample_engine_outputs.facility_capabilities = {
        "F2": ["maternity"],
    }
    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 16, tzinfo=timezone.utc))

    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT capability FROM operational.facility_capabilities "
            "WHERE facility_id = 'F2'"
        )).fetchall()
    assert {r.capability for r in rows} == {"maternity"}
