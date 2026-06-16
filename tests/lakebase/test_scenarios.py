"""Tests for LP-SCEN-* — scenario save/restore."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text


def _seed_one_override(engine, sample_engine_outputs, planner_id) -> str:
    from phantom_census.lakebase.writer import load_engine_outputs
    from phantom_census.lakebase.overrides import submit_override
    load_engine_outputs(sample_engine_outputs, engine,
                        ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO operational.desert_scores
            (district_id, district_name, state_name, capability,
             raw_desert_score, adjusted_desert_score,
             verified_facility_count, phantom_count, burden_imputed,
             nfhs_missing, burden_weight, max_density, updated_at)
            VALUES ('BEED','Beed','Maharashtra','maternity',0.6,0.78,12,4,
                    FALSE, FALSE, 0.3, 80, NOW())
        """))
        conn.execute(text(
            "INSERT INTO operational.facility_district_xref (facility_id, district_id) "
            "VALUES ('F2','BEED')"
        ))
    oid, _district = submit_override(
        engine, facility_id="F2", override_type="force-real",
        reason_note="visited", planner_id=planner_id,
        recompute_fn=lambda *a, **kw: None,
    )
    return oid


# @spec LP-SCEN-001
def test_save_scenario_returns_uuid(engine, sample_engine_outputs, fresh_planner_id):
    from phantom_census.lakebase.scenarios import save_scenario
    oid = _seed_one_override(engine, sample_engine_outputs, fresh_planner_id)
    sid = save_scenario(engine,
                        scenario_name="Maharashtra Q3 plan",
                        capability="maternity",
                        region_filter="Maharashtra",
                        override_ids=[oid],
                        planner_notes="initial pass",
                        planner_id=fresh_planner_id)
    assert isinstance(sid, str)


# @spec LP-SCEN-002
def test_get_saved_scenarios_filtered_by_planner(engine, sample_engine_outputs, fresh_planner_id):
    from phantom_census.lakebase.scenarios import save_scenario
    from phantom_census.lakebase.readers import get_saved_scenarios
    oid = _seed_one_override(engine, sample_engine_outputs, fresh_planner_id)
    save_scenario(engine,
                  scenario_name="mine",
                  capability="maternity",
                  region_filter="Maharashtra",
                  override_ids=[oid],
                  planner_notes="",
                  planner_id=fresh_planner_id)
    save_scenario(engine,
                  scenario_name="someone-else",
                  capability="maternity",
                  region_filter="Maharashtra",
                  override_ids=[oid],
                  planner_notes="",
                  planner_id="other-planner")

    df = get_saved_scenarios(engine, planner_id=fresh_planner_id)
    names = set(df["scenario_name"])
    assert "mine" in names
    assert "someone-else" not in names


# @spec LP-SCEN-003, LP-SCEN-004
def test_restore_scenario_reasserts_verdicts(engine, sample_engine_outputs, fresh_planner_id):
    """After restore, phantom_verdicts state matches what was saved (with the
    planner verdict enum value per LP-SCHEMA-VERDICT-002)."""
    from phantom_census.lakebase.scenarios import save_scenario, restore_scenario
    oid = _seed_one_override(engine, sample_engine_outputs, fresh_planner_id)
    sid = save_scenario(engine,
                        scenario_name="snap",
                        capability="maternity",
                        region_filter="Maharashtra",
                        override_ids=[oid],
                        planner_notes="",
                        planner_id=fresh_planner_id)

    # Mutate state — verdict regresses
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE operational.phantom_verdicts SET verdict='phantom', override_id=NULL "
            "WHERE facility_id='F2'"
        ))

    restore_scenario(engine, scenario_id=sid, recompute_fn=lambda *a, **kw: None)

    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT verdict, override_id FROM operational.phantom_verdicts WHERE facility_id='F2'"
        )).first()
    assert row.verdict == "force-real-planner"
    assert row.override_id == oid


# @spec LP-SCEN-005
def test_restore_scenario_preserves_ai_recommendation_columns(
    engine, sample_engine_outputs, fresh_planner_id,
):
    """LP-SCEN-005 (new): scenario restore does not touch ai_recommendation or
    ai_recommendation_evidence_state."""
    from phantom_census.lakebase.scenarios import save_scenario, restore_scenario
    oid = _seed_one_override(engine, sample_engine_outputs, fresh_planner_id)
    sid = save_scenario(engine, scenario_name="snap", capability="maternity",
                        region_filter="Maharashtra", override_ids=[oid],
                        planner_notes="", planner_id=fresh_planner_id)

    # Pre-populate AI cache columns to test preservation.
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE operational.phantom_verdicts SET
                ai_recommendation = CAST(:rec AS JSONB),
                ai_recommendation_evidence_state = :state,
                verdict = 'phantom', override_id = NULL
            WHERE facility_id = 'F2'
        """), {
            "rec": '{"recommendation": "force-real", "confidence": "low",'
                   ' "reasoning": "x", "cited_evidence_rows": [], "source": "fma"}',
            "state": "cafebabe" * 8,
        })

    restore_scenario(engine, scenario_id=sid, recompute_fn=lambda *a, **kw: None)

    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT ai_recommendation, ai_recommendation_evidence_state "
            "FROM operational.phantom_verdicts WHERE facility_id='F2'"
        )).first()
    assert row.ai_recommendation is not None
    assert row.ai_recommendation_evidence_state == "cafebabe" * 8


# @spec LP-SCEN-003
def test_restore_scenario_is_no_op_when_state_already_matches(
    engine, sample_engine_outputs, fresh_planner_id
):
    from phantom_census.lakebase.scenarios import save_scenario, restore_scenario
    oid = _seed_one_override(engine, sample_engine_outputs, fresh_planner_id)
    sid = save_scenario(engine, scenario_name="snap", capability="maternity",
                        region_filter="Maharashtra", override_ids=[oid],
                        planner_notes="", planner_id=fresh_planner_id)

    # State already matches saved snapshot — restore should not re-recompute
    calls: list = []
    restore_scenario(engine, scenario_id=sid,
                     recompute_fn=lambda eng, district_id, capability: calls.append(district_id))
    assert calls == []
