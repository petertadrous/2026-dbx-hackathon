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
             verified_facility_count, phantom_count, burden_imputed, updated_at)
            VALUES ('BEED', 'Beed', 'Maharashtra', 'maternity',
                    0.6, 0.78, 12, 4, FALSE, NOW())
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
def test_apply_override_updates_phantom_verdicts(engine, sample_engine_outputs, fresh_planner_id):
    _seed_phantom_facility(engine, sample_engine_outputs)
    from phantom_census.lakebase.overrides import save_override, apply_override
    oid = save_override(engine, facility_id="F2", override_type="force-real",
                        reason_note="ok", planner_id=fresh_planner_id)
    apply_override(engine, override_id=oid, recompute_fn=lambda *a, **kw: None)
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT verdict, override_id FROM operational.phantom_verdicts WHERE facility_id='F2'"
        )).first()
    assert row.verdict == "real"
    assert row.override_id == oid


# @spec LP-OVR-003
def test_apply_override_calls_recompute_for_affected_district(
    engine, sample_engine_outputs, fresh_planner_id
):
    _seed_phantom_facility(engine, sample_engine_outputs)
    from phantom_census.lakebase.overrides import save_override, apply_override
    called: list = []
    oid = save_override(engine, facility_id="F2", override_type="force-real",
                        reason_note="ok", planner_id=fresh_planner_id)
    apply_override(engine, override_id=oid,
                   recompute_fn=lambda eng, district_id, capability: called.append(district_id))
    assert called == ["BEED"]


# @spec LP-OVR-004
def test_apply_override_rolls_back_on_recompute_failure(
    engine, sample_engine_outputs, fresh_planner_id
):
    _seed_phantom_facility(engine, sample_engine_outputs)
    from phantom_census.lakebase.overrides import save_override, apply_override
    oid = save_override(engine, facility_id="F2", override_type="force-real",
                        reason_note="ok", planner_id=fresh_planner_id)
    def boom(*a, **kw): raise RuntimeError("scoring exploded")
    with pytest.raises(RuntimeError):
        apply_override(engine, override_id=oid, recompute_fn=boom)
    # Verdict should NOT have changed if recompute failed
    with engine.begin() as conn:
        v = conn.execute(text(
            "SELECT verdict FROM operational.phantom_verdicts WHERE facility_id='F2'"
        )).scalar_one()
    assert v == "phantom"
