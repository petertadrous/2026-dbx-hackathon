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
def test_submit_override_updates_phantom_verdicts(engine, sample_engine_outputs, fresh_planner_id):
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
    assert row.verdict == "real"
    assert row.override_id == oid
    assert district == "BEED"


# @spec LP-OVR-003
def test_submit_override_calls_recompute_for_affected_district(
    engine, sample_engine_outputs, fresh_planner_id
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
        recompute_fn=lambda conn, district_id, capability: called.append(district_id),
    )
    assert called == ["BEED"]


# @spec LP-OVR-004
def test_submit_override_rolls_back_audit_and_verdict_on_recompute_failure(
    engine, sample_engine_outputs, fresh_planner_id
):
    """Every write — audit row, verdict update, score recompute — must commit
    or roll back together. A recompute that raises must leave NO rows behind:
    the verdict stays `phantom` AND no orphan row lands in planner_overrides."""
    _seed_phantom_facility(engine, sample_engine_outputs)
    from phantom_census.lakebase.overrides import submit_override

    def boom(conn, district_id, capability):
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
    assert n_overrides == 0  # audit row rolled back too


# @spec LP-OVR-004 — recompute that writes via the same Connection also rolls back
def test_submit_override_rolls_back_inner_writes_too(
    engine, sample_engine_outputs, fresh_planner_id
):
    _seed_phantom_facility(engine, sample_engine_outputs)
    from phantom_census.lakebase.overrides import submit_override

    def fake_recompute(conn, district_id, capability):
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
    assert phantom_count != 999, "inner recompute writes must roll back with outer TX"
