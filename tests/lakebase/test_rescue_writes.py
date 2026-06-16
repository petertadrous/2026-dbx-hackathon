"""Tests for LP-RESCUE-* — Defender Layer A persistence."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text


def _seed_phantom(engine, sample_engine_outputs):
    from phantom_census.lakebase.writer import load_engine_outputs
    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))


# @spec LP-RESCUE-001
def test_layer_a_rescue_patches_verdict_and_writes_rescue_applied(
    engine, sample_engine_outputs,
):
    _seed_phantom(engine, sample_engine_outputs)
    from phantom_census.lakebase.rescue_writes import apply_layer_a_rescue
    apply_layer_a_rescue(engine, facility_id="F2", rescue_applied={
        "signals": [{"signal": "hfr-match"}],
        "evidence_refs": ["hfr-row-42"],
    })
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT verdict, adjudicator_verdict, rescue_applied "
            "FROM operational.phantom_verdicts WHERE facility_id='F2'"
        )).first()
    assert row.verdict == "contested"
    assert row.adjudicator_verdict == "phantom"
    assert row.rescue_applied is not None


# @spec LP-RESCUE-002
def test_layer_a_rescue_does_not_write_facility_existence_tests_row(
    engine, sample_engine_outputs,
):
    _seed_phantom(engine, sample_engine_outputs)
    from phantom_census.lakebase.rescue_writes import apply_layer_a_rescue
    with engine.begin() as conn:
        before = conn.execute(text(
            "SELECT COUNT(*) FROM operational.facility_existence_tests"
        )).scalar_one()
    apply_layer_a_rescue(engine, facility_id="F2", rescue_applied={
        "signals": [{"signal": "url-mentions"}],
        "evidence_refs": [],
    })
    with engine.begin() as conn:
        after = conn.execute(text(
            "SELECT COUNT(*) FROM operational.facility_existence_tests"
        )).scalar_one()
    assert before == after
