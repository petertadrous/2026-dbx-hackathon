"""App-side read paths.

@spec LP-APP-001, LP-APP-002, LP-APP-003, LP-SCEN-002
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
    """Return up to `limit` phantom-verdicted facilities in the given district.

    Joins `facility_district_xref` (populated by the engine writer) so the
    request path does not have to rejoin the ADM2 polygons.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT pv.facility_id, pv.verdict, pv.reason, pv.test_outcome_vector "
                "FROM operational.phantom_verdicts pv "
                "JOIN operational.facility_district_xref x USING (facility_id) "
                "WHERE x.district_id = :district_id "
                "  AND pv.verdict = 'phantom' "
                "ORDER BY pv.facility_id "
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
                "ORDER BY test_name"
            ),
            {"facility_id": facility_id},
        ).mappings().all()
    return pd.DataFrame(rows)


def get_tile_html(engine: Engine, capability: str, layer_type: str) -> str | None:
    """Read a pre-rendered Folium choropleth HTML string from cache.tile_layers."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT html FROM cache.tile_layers "
                "WHERE capability = :capability AND layer_type = :layer_type"
            ),
            {"capability": capability, "layer_type": layer_type},
        ).first()
    return row.html if row else None


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
