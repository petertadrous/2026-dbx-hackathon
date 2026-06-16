"""Tests for LP-OVR-* — override write path."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text


def _seed_phantom_facility(engine, sample_engine_outputs):
    from phantom_census.lakebase.writer import load_engine_outputs
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
            VALUES ('F2', 'BEED')
        """))


# @spec LP-OVR-001
def test_save_override_returns_new_uuid(engine, sample_engine_outputs, fresh_planner_id):
    _seed_phantom_facility(engine, sample_engine_outputs)
    from phantom_census.lakebase.overrides import save_override
    oid = save_override(engine,
                        facility_id="F2",
                        override_type="force-real",
                        reason_note="Verified on-site visit",
                        planner_id=fresh_planner_id)
    assert isinstance(oid, str)
    assert len(oid) >= 16


# @spec LP-OVR-002
def test_submit_override_writes_planner_verdict_value(
    engine, sample_engine_outputs, fresh_planner_id,
):
    """LP-OVR-002 (refined): verdict is set to 'force-real-planner' or
    'force-phantom-planner' (per LP-SCHEMA-VERDICT-002), not 'real'/'phantom'."""
    _seed_phantom_facility(engine, sample_engine_outputs)
    from phantom_census.lakebase.overrides import submit_override
    oid, district = submit_override(
        engine,
        facility_id="F2",
        override_type="force-real",
        reason_note="ok",
        planner_id=fresh_planner_id,
        recompute_fn=lambda *a, **kw: None,
    )
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT verdict, override_id FROM operational.phantom_verdicts WHERE facility_id='F2'"
        )).first()
    assert row.verdict == "force-real-planner"
    assert row.override_id == oid
    assert district == "BEED"


# @spec LP-OVR-003
def test_submit_override_preserves_adjudicator_verdict_and_rescue_and_ai_columns(
    engine, sample_engine_outputs, fresh_planner_id,
):
    """LP-OVR-003 (inverted!): preserve adjudicator_verdict, rescue_applied,
    ai_recommendation, ai_recommendation_evidence_state when LP-OVR-002 runs."""
    _seed_phantom_facility(engine, sample_engine_outputs)
    # Pre-populate rescue + AI columns for F2.
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE operational.phantom_verdicts SET
                rescue_applied = CAST(:rescue AS JSONB),
                ai_recommendation = CAST(:rec AS JSONB),
                ai_recommendation_evidence_state = :state
            WHERE facility_id = 'F2'
        """), {
            "rescue": '{"signals": [{"signal": "hfr-match"}], "evidence_refs": []}',
            "rec": '{"recommendation": "force-phantom", "confidence": "medium",'
                   ' "reasoning": "x", "cited_evidence_rows": [], "source": "fma"}',
            "state": "feedface" * 8,
        })

    from phantom_census.lakebase.overrides import submit_override
    submit_override(
        engine,
        facility_id="F2",
        override_type="force-real",
        reason_note="planner reviewed",
        planner_id=fresh_planner_id,
        recompute_fn=lambda *a, **kw: None,
    )

    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT adjudicator_verdict, rescue_applied, ai_recommendation, "
            "       ai_recommendation_evidence_state "
            "FROM operational.phantom_verdicts WHERE facility_id='F2'"
        )).first()
    assert row.adjudicator_verdict == "phantom"  # untouched
    assert row.rescue_applied is not None
    assert row.ai_recommendation is not None
    assert row.ai_recommendation_evidence_state == "feedface" * 8


# @spec LP-OVR-004
def test_submit_override_calls_recompute_for_affected_district(
    engine, sample_engine_outputs, fresh_planner_id,
):
    _seed_phantom_facility(engine, sample_engine_outputs)
    from phantom_census.lakebase.overrides import submit_override
    called: list = []
    submit_override(
        engine,
        facility_id="F2",
        override_type="force-real",
        reason_note="ok",
        planner_id=fresh_planner_id,
        recompute_fn=lambda conn, district_id, capability, **kw: called.append(district_id),
    )
    assert called == ["BEED"]


# @spec LP-OVR-005
def test_submit_override_rolls_back_audit_and_verdict_on_recompute_failure(
    engine, sample_engine_outputs, fresh_planner_id,
):
    _seed_phantom_facility(engine, sample_engine_outputs)
    from phantom_census.lakebase.overrides import submit_override

    def boom(conn, district_id, capability, **kw):
        raise RuntimeError("scoring exploded")

    with pytest.raises(RuntimeError):
        submit_override(
            engine,
            facility_id="F2",
            override_type="force-real",
            reason_note="ok",
            planner_id=fresh_planner_id,
            recompute_fn=boom,
        )

    with engine.begin() as conn:
        v_row = conn.execute(text(
            "SELECT verdict, override_id FROM operational.phantom_verdicts "
            "WHERE facility_id='F2'"
        )).first()
        n_overrides = conn.execute(text(
            "SELECT COUNT(*) FROM team.planner_overrides WHERE planner_id=:p"
        ), {"p": fresh_planner_id}).scalar_one()
    assert v_row.verdict == "phantom"
    assert v_row.override_id is None
    assert n_overrides == 0


# @spec LP-OVR-005
def test_submit_override_rolls_back_inner_writes_too(
    engine, sample_engine_outputs, fresh_planner_id,
):
    _seed_phantom_facility(engine, sample_engine_outputs)
    from phantom_census.lakebase.overrides import submit_override

    def fake_recompute(conn, district_id, capability, **kw):
        conn.execute(text(
            "UPDATE operational.desert_scores SET phantom_count = 999 "
            "WHERE district_id=:d AND capability=:c"
        ), {"d": district_id, "c": capability})
        raise RuntimeError("scoring exploded after touching desert_scores")

    with pytest.raises(RuntimeError):
        submit_override(
            engine,
            facility_id="F2",
            override_type="force-real",
            reason_note="ok",
            planner_id=fresh_planner_id,
            recompute_fn=fake_recompute,
        )

    with engine.begin() as conn:
        phantom_count = conn.execute(text(
            "SELECT phantom_count FROM operational.desert_scores "
            "WHERE district_id='BEED' AND capability='maternity'"
        )).scalar_one()
    assert phantom_count != 999


# @spec LP-OVR-006
def test_repeat_override_appends_new_row_and_supersedes_pointer(
    engine, sample_engine_outputs, fresh_planner_id,
):
    """LP-OVR-006 (new): team.planner_overrides is append-only. A second override
    creates a new row; older rows remain; only phantom_verdicts.override_id
    advances to the most recent row."""
    _seed_phantom_facility(engine, sample_engine_outputs)
    from phantom_census.lakebase.overrides import submit_override
    oid1, _ = submit_override(
        engine, facility_id="F2", override_type="force-real",
        reason_note="first pass", planner_id=fresh_planner_id,
        recompute_fn=lambda *a, **kw: None,
    )
    oid2, _ = submit_override(
        engine, facility_id="F2", override_type="force-phantom",
        reason_note="changed my mind", planner_id=fresh_planner_id,
        recompute_fn=lambda *a, **kw: None,
    )
    assert oid1 != oid2

    with engine.begin() as conn:
        n = conn.execute(text(
            "SELECT COUNT(*) FROM team.planner_overrides WHERE facility_id='F2'"
        )).scalar_one()
        pointer = conn.execute(text(
            "SELECT override_id FROM operational.phantom_verdicts WHERE facility_id='F2'"
        )).scalar_one()
    assert n == 2
    assert pointer == oid2
