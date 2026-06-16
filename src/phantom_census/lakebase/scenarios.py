"""Scenario save/restore.

@spec LP-SCEN-001, LP-SCEN-002, LP-SCEN-003, LP-SCEN-004
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import Engine, text

_VERDICT_BY_TYPE = {"force-real": "real", "force-phantom": "phantom"}


# @spec LP-SCEN-001
def save_scenario(
    engine: Engine,
    *,
    scenario_name: str,
    capability: str,
    region_filter: str | None,
    override_ids: list[str],
    planner_notes: str,
    planner_id: str,
    saved_at: datetime | None = None,
) -> str:
    """Persist a scenario snapshot — returns new scenario_id."""
    scenario_id = uuid.uuid4().hex
    saved_at = saved_at or datetime.now(tz=timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO team.saved_scenarios
                    (scenario_id, scenario_name, capability, region_filter,
                     override_set, planner_notes, planner_id, saved_at)
                VALUES
                    (:scenario_id, :scenario_name, :capability, :region_filter,
                     CAST(:override_set AS JSONB),
                     :planner_notes, :planner_id, :saved_at)
            """),
            {
                "scenario_id": scenario_id,
                "scenario_name": scenario_name,
                "capability": capability,
                "region_filter": region_filter,
                "override_set": json.dumps(override_ids),
                "planner_notes": planner_notes,
                "planner_id": planner_id,
                "saved_at": saved_at,
            },
        )
    return scenario_id


# @spec LP-SCEN-003, LP-SCEN-004
def restore_scenario(
    engine: Engine,
    *,
    scenario_id: str,
    recompute_fn: Callable[[Engine, str, str], None],
) -> list[str]:
    """Re-assert the override set for scenario_id onto phantom_verdicts.

    A row whose effective verdict + override_id already matches the saved
    state is a no-op (LP-SCEN-003). Districts touched by any reassertion are
    passed to ``recompute_fn`` exactly once. Returns the list of district_ids
    actually recomputed.
    """
    with engine.begin() as conn:
        scenario_row = conn.execute(
            text("SELECT capability, override_set FROM team.saved_scenarios "
                 "WHERE scenario_id = :sid"),
            {"sid": scenario_id},
        ).first()
        if scenario_row is None:
            raise LookupError(f"scenario_id not found: {scenario_id}")

        capability = scenario_row.capability
        override_set = scenario_row.override_set
        if isinstance(override_set, str):
            override_set = json.loads(override_set)

        touched_districts: list[str] = []

        for oid in override_set:
            override = conn.execute(
                text("SELECT facility_id, override_type "
                     "FROM team.planner_overrides WHERE override_id = :oid"),
                {"oid": oid},
            ).first()
            if override is None:
                continue
            target_verdict = _VERDICT_BY_TYPE[override.override_type]

            current = conn.execute(
                text("SELECT verdict, override_id "
                     "FROM operational.phantom_verdicts WHERE facility_id = :fid"),
                {"fid": override.facility_id},
            ).first()
            if current and current.verdict == target_verdict and current.override_id == oid:
                # No-op per LP-SCEN-003
                continue

            conn.execute(
                text("UPDATE operational.phantom_verdicts "
                     "SET verdict = :v, override_id = :o WHERE facility_id = :f"),
                {"v": target_verdict, "o": oid, "f": override.facility_id},
            )

            district_row = conn.execute(
                text("SELECT district_id FROM operational.facility_district_xref "
                     "WHERE facility_id = :fid"),
                {"fid": override.facility_id},
            ).first()
            if district_row and district_row.district_id not in touched_districts:
                touched_districts.append(district_row.district_id)

        for district_id in touched_districts:
            recompute_fn(engine, district_id, capability)

    return touched_districts
