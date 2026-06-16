"""Tests for LP-AI-CACHE-* — AI Evidence Layer write path."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text


def _seed(engine, sample_engine_outputs):
    from phantom_census.lakebase.writer import load_engine_outputs
    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))


# @spec LP-AI-CACHE-001
def test_persist_ai_recommendation_writes_jsonb_and_hash(engine, sample_engine_outputs):
    _seed(engine, sample_engine_outputs)
    from phantom_census.lakebase.ai_cache_writes import persist_ai_recommendation
    persist_ai_recommendation(
        engine, facility_id="F2",
        recommendation={
            "recommendation": "force-phantom", "confidence": "high",
            "reasoning": "model output", "cited_evidence_rows": ["a"], "source": "fma",
        },
        evidence_state="deadbeef" * 8,
    )
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT ai_recommendation, ai_recommendation_evidence_state "
            "FROM operational.phantom_verdicts WHERE facility_id='F2'"
        )).first()
    assert row.ai_recommendation is not None
    assert row.ai_recommendation_evidence_state == "deadbeef" * 8


# @spec LP-AI-CACHE-003
def test_persist_ai_recommendation_does_not_touch_other_columns(engine, sample_engine_outputs):
    _seed(engine, sample_engine_outputs)
    from phantom_census.lakebase.ai_cache_writes import persist_ai_recommendation
    persist_ai_recommendation(
        engine, facility_id="F2",
        recommendation={
            "recommendation": "force-phantom", "confidence": "high",
            "reasoning": "x", "cited_evidence_rows": [], "source": "fma",
        },
        evidence_state="cafebabe" * 8,
    )
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT verdict, adjudicator_verdict, rescue_applied, "
            "       test_outcome_vector, override_id "
            "FROM operational.phantom_verdicts WHERE facility_id='F2'"
        )).first()
    assert row.verdict == "phantom"
    assert row.adjudicator_verdict == "phantom"
    assert row.override_id is None


# @spec LP-AI-CACHE-005
def test_persist_ai_recommendation_skips_when_override_landed(engine, sample_engine_outputs):
    """LP-AI-CACHE-005: persistence write is guarded by override_id IS NULL —
    if a planner override lands while FMA was in flight, the write is skipped."""
    _seed(engine, sample_engine_outputs)
    # Pre-existing override (the override-races-FMA case).
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO team.planner_overrides
                (override_id, facility_id, override_type, reason_note,
                 planner_id, overridden_at)
            VALUES ('ovr-1', 'F2', 'force-phantom', 'because', 'planner-x', NOW())
        """))
        conn.execute(text("""
            UPDATE operational.phantom_verdicts SET override_id='ovr-1'
            WHERE facility_id='F2'
        """))

    from phantom_census.lakebase.ai_cache_writes import persist_ai_recommendation
    persist_ai_recommendation(
        engine, facility_id="F2",
        recommendation={
            "recommendation": "force-real", "confidence": "high",
            "reasoning": "late arrival", "cited_evidence_rows": [], "source": "fma",
        },
        evidence_state="badcoded" * 8,
    )

    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT ai_recommendation, ai_recommendation_evidence_state "
            "FROM operational.phantom_verdicts WHERE facility_id='F2'"
        )).first()
    # Persistence was suppressed by the override-races-FMA guard.
    assert row.ai_recommendation is None
    assert row.ai_recommendation_evidence_state is None
