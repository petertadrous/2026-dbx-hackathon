"""Tests for LP-APP-* — app read paths."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text


# @spec LP-APP-001
def test_get_desert_scores_for_capability(maharashtra_districts):
    from phantom_census.lakebase.readers import get_desert_scores
    df = get_desert_scores(maharashtra_districts, capability="maternity")
    assert len(df) == 2
    assert set(df["district_id"]) == {"BEED", "MUM"}


# @spec LP-APP-002
def test_get_district_phantoms_returns_top_five(engine, sample_engine_outputs):
    from phantom_census.lakebase.writer import load_engine_outputs
    from phantom_census.lakebase.readers import get_district_phantoms

    # Seed verdicts so F2 (phantom) is attached to BEED via the join helper.
    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO operational.desert_scores
            (district_id, district_name, state_name, capability,
             raw_desert_score, adjusted_desert_score,
             verified_facility_count, phantom_count, burden_imputed,
             nfhs_missing, burden_weight, max_density, updated_at)
            VALUES ('BEED', 'Beed', 'Maharashtra', 'maternity',
                    0.6, 0.78, 12, 4, FALSE, FALSE, 0.3, 80, NOW())
        """))
        conn.execute(text("""
            INSERT INTO operational.facility_district_xref (facility_id, district_id)
            VALUES ('F2', 'BEED'), ('F1', 'BEED')
        """))
    rows = get_district_phantoms(engine, district_id="BEED", limit=5)
    assert "F2" in set(rows["facility_id"])
    assert "F1" not in set(rows["facility_id"])  # F1 is real, not phantom


# @spec LP-APP-003
def test_get_facility_tests_returns_all_rows_for_facility(engine, sample_engine_outputs):
    from phantom_census.lakebase.writer import load_engine_outputs
    from phantom_census.lakebase.readers import get_facility_tests

    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    df = get_facility_tests(engine, facility_id="F1")
    assert len(df) == 5
    assert set(df["test_name"]) == {
        "pin-reverse-lookup", "minhash-near-duplicate",
        "spatial-district-mismatch", "nfhs-outcome-inconsistency",
        "temporal-implausibility",
    }
