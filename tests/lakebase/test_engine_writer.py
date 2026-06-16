"""Tests for LP-EE-* — engine output → Lakebase."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest
from datasketch import MinHash
from sqlalchemy import text


# @spec LP-EE-001
def test_writer_inserts_one_row_per_test_per_facility(engine, sample_engine_outputs):
    from phantom_census.lakebase.writer import load_engine_outputs
    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    with engine.begin() as conn:
        n = conn.execute(text(
            "SELECT COUNT(*) FROM operational.facility_existence_tests"
        )).scalar_one()
    # 2 facilities × 6 tests now (Test 6 embedding-drift is included)
    assert n == 12


# @spec LP-EE-002
def test_writer_inserts_one_verdict_per_facility(engine, sample_engine_outputs):
    from phantom_census.lakebase.writer import load_engine_outputs
    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT facility_id, adjudicator_verdict, verdict "
            "FROM operational.phantom_verdicts ORDER BY facility_id"
        )).fetchall()
    assert [r.facility_id for r in rows] == ["F1", "F2"]
    assert [r.adjudicator_verdict for r in rows] == ["real", "phantom"]
    assert [r.verdict for r in rows] == ["real", "phantom"]


# @spec LP-EE-002
def test_writer_overwrites_prior_verdict_on_rerun(engine, sample_engine_outputs):
    from phantom_census.lakebase.writer import load_engine_outputs
    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    sample_engine_outputs.phantom_verdicts.loc[
        sample_engine_outputs.phantom_verdicts["facility_id"] == "F2", "verdict"
    ] = "contested"
    sample_engine_outputs.phantom_verdicts.loc[
        sample_engine_outputs.phantom_verdicts["facility_id"] == "F2",
        "adjudicator_verdict",
    ] = "contested"
    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 16, tzinfo=timezone.utc))
    with engine.begin() as conn:
        n = conn.execute(text(
            "SELECT COUNT(*) FROM operational.phantom_verdicts"
        )).scalar_one()
        v = conn.execute(text(
            "SELECT verdict FROM operational.phantom_verdicts WHERE facility_id='F2'"
        )).scalar_one()
    assert n == 2
    assert v == "contested"


# @spec LP-EE-002
def test_writer_preserves_ai_recommendation_and_override_id_on_rerun(
    engine, sample_engine_outputs,
):
    """LP-EE-002 refined: on re-batch, AI cache columns and override_id
    must be PRESERVED unchanged (not cleared)."""
    from phantom_census.lakebase.writer import load_engine_outputs
    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))

    # Simulate an AI Evidence Layer write + a planner override landing between batches.
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE operational.phantom_verdicts SET
                ai_recommendation = CAST(:rec AS JSONB),
                ai_recommendation_evidence_state = :state,
                override_id = :oid
            WHERE facility_id = 'F2'
        """), {
            "rec": '{"recommendation": "force-phantom", "confidence": "low",'
                   ' "reasoning": "x", "cited_evidence_rows": [], "source": "fma"}',
            "state": "deadbeef" * 8,
            "oid": "ovr-pre-existing",
        })

    # Re-batch with same data — the writer must NOT clear those columns.
    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 16, tzinfo=timezone.utc))

    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT ai_recommendation, ai_recommendation_evidence_state, override_id "
            "FROM operational.phantom_verdicts WHERE facility_id='F2'"
        )).first()
    assert row.ai_recommendation is not None
    assert row.ai_recommendation_evidence_state == "deadbeef" * 8
    assert row.override_id == "ovr-pre-existing"


# @spec LP-EE-002
def test_writer_initializes_ai_and_override_columns_to_null_on_first_insert(
    engine, sample_engine_outputs,
):
    from phantom_census.lakebase.writer import load_engine_outputs
    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT ai_recommendation, ai_recommendation_evidence_state, "
            "       override_id, rescue_applied, layer_c_synthesis "
            "FROM operational.phantom_verdicts WHERE facility_id='F1'"
        )).first()
    assert row.ai_recommendation is None
    assert row.ai_recommendation_evidence_state is None
    assert row.override_id is None
    assert row.rescue_applied is None
    assert row.layer_c_synthesis is None


# @spec LP-EE-003
def test_writer_persists_minhash_signatures_as_bytea(engine, sample_engine_outputs):
    from phantom_census.lakebase.writer import load_engine_outputs
    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT facility_id, signature FROM cache.claim_minhash ORDER BY facility_id"
        )).fetchall()
    assert {r.facility_id for r in rows} == {"F1", "F2"}
    for r in rows:
        assert isinstance(r.signature, (bytes, memoryview))
        assert len(bytes(r.signature)) == 128 * 4


# @spec LP-EE-003
def test_writer_round_trips_signature_jaccard(engine, sample_engine_outputs):
    from phantom_census.lakebase.writer import load_engine_outputs
    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    with engine.begin() as conn:
        sig_bytes = bytes(conn.execute(text(
            "SELECT signature FROM cache.claim_minhash WHERE facility_id='F1'"
        )).scalar_one())
    restored = MinHash(num_perm=128,
                       hashvalues=np.frombuffer(sig_bytes, dtype=np.uint32))
    assert restored.jaccard(sample_engine_outputs.claim_minhash_signatures["F1"]) == 1.0


# @spec LP-EE-004
def test_writer_persists_description_embeddings(engine, sample_engine_outputs):
    """LP-EE-004 (new): one row per (facility_id, snapshot_id) with 384-dim BYTEA."""
    from phantom_census.lakebase.writer import load_engine_outputs
    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT facility_id, snapshot_id, embedding "
            "FROM cache.description_embeddings ORDER BY facility_id"
        )).fetchall()
    assert {r.facility_id for r in rows} == {"F1", "F2"}
    for r in rows:
        assert r.snapshot_id == "2026-06-15-batch-001"
        assert len(bytes(r.embedding)) == 384 * 4


# @spec LP-EE-005
def test_writer_rolls_back_entire_batch_on_inner_failure(engine, sample_engine_outputs):
    from phantom_census.lakebase.writer import load_engine_outputs
    sample_engine_outputs.phantom_verdicts.loc[
        sample_engine_outputs.phantom_verdicts["facility_id"] == "F2", "verdict"
    ] = "this-verdict-string-is-far-too-long"
    with pytest.raises(Exception):
        load_engine_outputs(sample_engine_outputs, engine,
                            ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    with engine.begin() as conn:
        n_tests = conn.execute(text(
            "SELECT COUNT(*) FROM operational.facility_existence_tests"
        )).scalar_one()
        n_verdicts = conn.execute(text(
            "SELECT COUNT(*) FROM operational.phantom_verdicts"
        )).scalar_one()
        n_sigs = conn.execute(text(
            "SELECT COUNT(*) FROM cache.claim_minhash"
        )).scalar_one()
        n_emb = conn.execute(text(
            "SELECT COUNT(*) FROM cache.description_embeddings"
        )).scalar_one()
    assert n_tests == 0
    assert n_verdicts == 0
    assert n_sigs == 0
    assert n_emb == 0
