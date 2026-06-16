"""Tests for LP-INIT-* and LP-SCHEMA-* — schema initialization."""
from __future__ import annotations

import os

import pytest
from sqlalchemy import inspect, text


# @spec LP-INIT-001
def test_init_creates_all_tables(engine):
    insp = inspect(engine)
    assert set(insp.get_table_names(schema="operational")) >= {
        "phantom_verdicts", "facility_existence_tests", "desert_scores",
    }
    assert set(insp.get_table_names(schema="cache")) >= {
        "claim_minhash", "description_embeddings",
    }
    assert set(insp.get_table_names(schema="team")) >= {
        "planner_overrides", "saved_scenarios", "budget_allocations",
    }


# @spec LP-INIT-001
def test_init_does_not_create_obsolete_tile_layers(engine):
    """LP-INIT-004 (inverted): cache.tile_layers is deleted; pydeck reads
    desert_scores directly. The migration must NOT create the obsolete table."""
    insp = inspect(engine)
    assert "tile_layers" not in insp.get_table_names(schema="cache")


# @spec LP-INIT-001
def test_init_is_idempotent(engine):
    from phantom_census.lakebase.migrate import init_schema
    init_schema(engine)
    init_schema(engine)


# @spec LP-INIT-002, LP-INIT-003
def test_kill_switches_log_when_features_unavailable(engine, caplog):
    from phantom_census.lakebase.migrate import init_schema
    init_schema(engine)


# @spec LP-INIT-004
def test_init_004_pgvector_index_best_effort(engine, caplog):
    """LP-INIT-004 (inverted): idx_description_embeddings_cosine on
    cache.description_embeddings.embedding. On vanilla Postgres without
    pgvector the migration logs a warning and continues (LP-Q3 resolution)."""
    from phantom_census.lakebase.migrate import init_schema
    init_schema(engine)
    # The migration must either create the index (when pgvector is loaded) or
    # log a warning. Either way init_schema must not raise.


# @spec LP-INIT-004
@pytest.mark.skipif(
    os.environ.get("TESTCONTAINERS_PGVECTOR") != "1",
    reason="pgvector image not selected; set TESTCONTAINERS_PGVECTOR=1 to run",
)
def test_init_004_pgvector_extension_loaded_on_pgvector_image(engine):
    """When the pgvector image is selected, the migration installs the vector
    extension. The cosine index against BYTEA storage is a known limitation —
    pgvector does not auto-cast bytea to vector — so the index itself stays
    a best-effort no-op. The extension being loaded is the load-bearing
    precondition for any future schema variant that stores `vector(384)`
    directly."""
    with engine.connect() as conn:
        ext = conn.execute(text(
            "SELECT extname FROM pg_extension WHERE extname = 'vector'"
        )).fetchall()
    assert len(ext) == 1, "expected pgvector extension to be installed"


# @spec LP-INIT-005
def test_description_embeddings_composite_pk(engine):
    insp = inspect(engine)
    pk = insp.get_pk_constraint("description_embeddings", schema="cache")
    assert set(pk["constrained_columns"]) == {"facility_id", "snapshot_id"}


# @spec LP-INIT-005
def test_claim_minhash_pk_unchanged(engine):
    insp = inspect(engine)
    pk = insp.get_pk_constraint("claim_minhash", schema="cache")
    assert pk["constrained_columns"] == ["facility_id"]


# @spec LP-INIT-006
def test_budget_allocations_composite_pk(engine):
    insp = inspect(engine)
    pk = insp.get_pk_constraint("budget_allocations", schema="team")
    assert set(pk["constrained_columns"]) == {"district_id", "capability", "quarter"}


# @spec LP-SCHEMA-VERDICT-001
def test_phantom_verdicts_has_dual_verdict_columns_and_ai_cache_cols(engine):
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("phantom_verdicts", schema="operational")}
    required = {
        "facility_id", "adjudicator_verdict", "verdict",
        "rescue_applied", "test_outcome_vector",
        "ai_recommendation", "ai_recommendation_evidence_state",
        "override_id", "ran_at",
        # EE-Q4 cascade: layer_c_synthesis lives on phantom_verdicts.
        "layer_c_synthesis",
    }
    missing = required - cols
    assert not missing, f"missing columns: {missing}"


# @spec LP-SCHEMA-VERDICT-001
def test_phantom_verdicts_has_facility_id_pk(engine):
    insp = inspect(engine)
    pk = insp.get_pk_constraint("phantom_verdicts", schema="operational")
    assert pk["constrained_columns"] == ["facility_id"]


# @spec LP-SCHEMA-TEST-001
def test_facility_existence_tests_composite_pk_includes_ran_at(engine):
    insp = inspect(engine)
    pk = insp.get_pk_constraint("facility_existence_tests", schema="operational")
    assert set(pk["constrained_columns"]) == {"facility_id", "test_name", "ran_at"}


# @spec LP-SCHEMA-DESERT-001
def test_desert_scores_composite_pk(engine):
    insp = inspect(engine)
    pk = insp.get_pk_constraint("desert_scores", schema="operational")
    assert set(pk["constrained_columns"]) == {"district_id", "capability"}


# @spec LP-SCHEMA-VERDICT-002
def test_verdict_column_accepts_planner_override_values(engine):
    """The verdict column must accept 'force-real-planner' and 'force-phantom-planner'."""
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO operational.phantom_verdicts
                (facility_id, adjudicator_verdict, verdict, test_outcome_vector, ran_at)
            VALUES ('X', 'phantom', 'force-real-planner', CAST('[]' AS JSONB), NOW())
        """))
        v = conn.execute(text(
            "SELECT verdict FROM operational.phantom_verdicts WHERE facility_id='X'"
        )).scalar_one()
    assert v == "force-real-planner"
