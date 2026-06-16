"""App-side read paths.

@spec LP-APP-001, LP-APP-002, LP-APP-003, LP-APP-004, LP-SCEN-002
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import Engine, text


# @spec LP-APP-001
def get_desert_scores(engine: Engine, capability: str) -> pd.DataFrame:
    """Read operational.desert_scores for a capability — drives the choropleth."""
    with engine.connect() as conn:
        return pd.DataFrame(
            conn.execute(
                text(
                    "SELECT district_id, district_name, state_name, capability, "
                    "raw_desert_score, adjusted_desert_score, "
                    "verified_facility_count, phantom_count, burden_imputed "
                    "FROM operational.desert_scores "
                    "WHERE capability = :capability"
                ),
                {"capability": capability},
            ).mappings().all()
        )


# @spec LP-APP-002
def get_district_phantoms(engine: Engine, district_id: str, limit: int = 5) -> pd.DataFrame:
    """Return up to `limit` phantom-or-contested facilities in the given district,
    leverage-ranked.

    LP-APP-002 refined:
      * SELECT now includes adjudicator_verdict, verdict, rescue_applied,
        ai_recommendation, override_id (in addition to the original four).
      * Filter broadens from `verdict = 'phantom'` to `verdict IN ('phantom',
        'contested')` — Defender Layer A's `contested` rescues belong in the
        side panel alongside phantoms.
      * ORDER BY leverage descending — LP-Q2 resolution maps the spec's
        ``mortality_burden × population × phantom_density`` to existing
        columns ``burden_weight × verified_facility_count × phantom_count``.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT pv.facility_id, pv.adjudicator_verdict, pv.verdict, "
                "       pv.reason, pv.test_outcome_vector, pv.rescue_applied, "
                "       pv.ai_recommendation, pv.override_id, "
                "       ds.burden_weight * ds.verified_facility_count * "
                "         GREATEST(ds.phantom_count, 1) AS leverage "
                "FROM operational.phantom_verdicts pv "
                "JOIN operational.facility_district_xref x USING (facility_id) "
                "JOIN operational.desert_scores ds "
                "  ON ds.district_id = x.district_id "
                "WHERE x.district_id = :district_id "
                "  AND pv.verdict IN ('phantom', 'contested') "
                "ORDER BY leverage DESC, pv.facility_id "
                "LIMIT :limit"
            ),
            {"district_id": district_id, "limit": limit},
        ).mappings().all()
    return pd.DataFrame(rows)


# @spec LP-APP-003
def get_facility_tests(engine: Engine, facility_id: str) -> pd.DataFrame:
    """All test rows for a facility — feeds the side panel's expand-evidence row."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT facility_id, test_name, result, evidence_ref, ran_at "
                "FROM operational.facility_existence_tests "
                "WHERE facility_id = :facility_id "
                "ORDER BY test_name, ran_at DESC"
            ),
            {"facility_id": facility_id},
        ).mappings().all()
    return pd.DataFrame(rows)


# @spec LP-APP-004
def get_available_capabilities(engine: Engine) -> list[str]:
    """SELECT DISTINCT capability FROM operational.desert_scores — populates the
    capability dropdown at app start. Cached by the app into
    ``st.session_state['available_capabilities']``."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT DISTINCT capability FROM operational.desert_scores "
            "ORDER BY capability"
        )).all()
    return [r[0] for r in rows]


# @spec LP-SCEN-002
def get_saved_scenarios(engine: Engine, planner_id: str) -> pd.DataFrame:
    """List a planner's saved scenarios, newest first."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT scenario_id, scenario_name, capability, region_filter, "
                "       planner_notes, saved_at "
                "FROM team.saved_scenarios "
                "WHERE planner_id = :planner_id "
                "ORDER BY saved_at DESC"
            ),
            {"planner_id": planner_id},
        ).mappings().all()
    return pd.DataFrame(rows)
