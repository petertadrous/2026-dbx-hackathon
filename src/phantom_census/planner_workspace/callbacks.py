"""Pure-Python callbacks used by the Streamlit views.

Keeping the side-effect logic out of `views/` makes the suite testable
without spinning up Streamlit.

@spec PW-OVR-003, PW-OVR-005, PW-SCEN-001, PW-SCEN-002, PW-SCEN-003
"""
from __future__ import annotations

from sqlalchemy import Engine

from phantom_census.desert_scoring.recompute import recompute_district
from phantom_census.lakebase.scenarios import restore_scenario, save_scenario
from phantom_census.lakebase.overrides import submit_override as _submit_override


# @spec PW-OVR-002, PW-OVR-003, PW-OVR-005
def submit_override(
    engine: Engine,
    *,
    facility_id: str,
    override_type: str,
    reason_note: str,
    planner_id: str,
    capability: str,
) -> str:
    """Append the audit row, update the verdict, and recompute the district
    in a single transaction — any failure rolls back all three (LP-OVR-004)."""
    if not reason_note or not reason_note.strip():
        raise ValueError("Reason note is required.")
    override_id, _district = _submit_override(
        engine,
        facility_id=facility_id,
        override_type=override_type,
        reason_note=reason_note,
        planner_id=planner_id,
        capability=capability,
        recompute_fn=recompute_district,
    )
    return override_id


# @spec PW-SCEN-001
def submit_scenario_save(
    engine: Engine,
    *,
    scenario_name: str,
    capability: str,
    region_filter: str | None,
    override_ids: list[str],
    planner_notes: str,
    planner_id: str,
) -> str:
    return save_scenario(
        engine,
        scenario_name=scenario_name,
        capability=capability,
        region_filter=region_filter,
        override_ids=override_ids,
        planner_notes=planner_notes,
        planner_id=planner_id,
    )


# @spec PW-SCEN-002, PW-SCEN-003, PW-SCEN-004
def restore(engine: Engine, *, scenario_id: str) -> list[str]:
    return restore_scenario(
        engine,
        scenario_id=scenario_id,
        recompute_fn=recompute_district,
    )
