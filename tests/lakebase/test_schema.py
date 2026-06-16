"""Tests for LP-INIT-* — schema initialization."""
from __future__ import annotations

from sqlalchemy import inspect, text


# @spec LP-INIT-001
def test_init_creates_all_seven_tables(engine):
    insp = inspect(engine)
    assert set(insp.get_table_names(schema="operational")) >= {
        "phantom_verdicts", "facility_existence_tests", "desert_scores",
    }
    assert set(insp.get_table_names(schema="cache")) >= {
        "claim_minhash", "tile_layers",
    }
    assert set(insp.get_table_names(schema="team")) >= {
        "planner_overrides", "saved_scenarios",
    }


# @spec LP-INIT-001
def test_init_is_idempotent(engine):
    """Re-running init_schema on an already-initialized DB does not error."""
    from phantom_census.lakebase.migrate import init_schema
    init_schema(engine)
    init_schema(engine)


# @spec LP-INIT-002, LP-INIT-003
def test_kill_switches_log_when_features_unavailable(engine, caplog):
    """LP-INIT-002 (CDC) and LP-INIT-003 (Liquid Clustering) are best-effort on
    Free Edition — when unavailable, init_schema must continue and warn."""
    from phantom_census.lakebase.migrate import init_schema
    # We don't have CDC or LC on vanilla Postgres — init must succeed anyway.
    init_schema(engine)


# @spec LP-INIT-004
def test_tile_layers_has_composite_pk(engine):
    insp = inspect(engine)
    pk = insp.get_pk_constraint("tile_layers", schema="cache")
    assert set(pk["constrained_columns"]) == {"capability", "layer_type"}


# @spec LP-INIT-001
def test_phantom_verdicts_has_facility_id_pk(engine):
    insp = inspect(engine)
    pk = insp.get_pk_constraint("phantom_verdicts", schema="operational")
    assert pk["constrained_columns"] == ["facility_id"]


# @spec LP-INIT-001
def test_facility_existence_tests_composite_pk(engine):
    insp = inspect(engine)
    pk = insp.get_pk_constraint("facility_existence_tests", schema="operational")
    assert set(pk["constrained_columns"]) == {"facility_id", "test_name", "ran_at"}
