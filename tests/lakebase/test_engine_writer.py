"""Tests for LP-EE-* — engine output → Lakebase."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
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
    assert n == 10  # 2 facilities × 5 tests


# @spec LP-EE-002
def test_writer_inserts_one_verdict_per_facility(engine, sample_engine_outputs):
    from phantom_census.lakebase.writer import load_engine_outputs
    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT facility_id, verdict FROM operational.phantom_verdicts ORDER BY facility_id"
        )).fetchall()
    assert [r.facility_id for r in rows] == ["F1", "F2"]
    assert [r.verdict for r in rows] == ["real", "phantom"]


# @spec LP-EE-002
def test_writer_overwrites_prior_verdict_on_rerun(engine, sample_engine_outputs):
    """Re-running the writer with a changed verdict must overwrite, not duplicate."""
    from phantom_census.lakebase.writer import load_engine_outputs
    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    sample_engine_outputs.phantom_verdicts.loc[
        sample_engine_outputs.phantom_verdicts["facility_id"] == "F2", "verdict"
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
def test_writer_atomic_per_facility(engine, sample_engine_outputs):
    """If a row in the test set is bad, no partial state remains for that batch."""
    from phantom_census.lakebase.writer import load_engine_outputs
    # Sabotage: drop the verdict for F1 so the writer cannot complete atomically
    sample_engine_outputs.phantom_verdicts = sample_engine_outputs.phantom_verdicts.iloc[1:].copy()
    try:
        load_engine_outputs(sample_engine_outputs, engine,
                            ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    except Exception:
        pass
    # After failure, no rows for F1 should exist anywhere
    with engine.begin() as conn:
        n_tests = conn.execute(text(
            "SELECT COUNT(*) FROM operational.facility_existence_tests WHERE facility_id='F1'"
        )).scalar_one()
        n_verdicts = conn.execute(text(
            "SELECT COUNT(*) FROM operational.phantom_verdicts WHERE facility_id='F1'"
        )).scalar_one()
    assert n_tests == 0
    assert n_verdicts == 0
