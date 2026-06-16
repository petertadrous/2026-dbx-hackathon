"""Override write path.

@spec LP-OVR-001, LP-OVR-002, LP-OVR-003, LP-OVR-004
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable, Literal

from sqlalchemy import Engine, text

OverrideType = Literal["force-real", "force-phantom"]

_VERDICT_BY_TYPE: dict[str, str] = {
    "force-real": "real",
    "force-phantom": "phantom",
}


# @spec LP-OVR-001
def save_override(
    engine: Engine,
    *,
    facility_id: str,
    override_type: OverrideType,
    reason_note: str,
    planner_id: str,
    overridden_at: datetime | None = None,
) -> str:
    """INSERT one row into team.planner_overrides; return new override_id.

    The append-only audit trail per LP-OVR-001 — older overrides remain in
    the table, superseded by newer ones on the same facility_id.
    """
    if override_type not in _VERDICT_BY_TYPE:
        raise ValueError(f"override_type must be one of {set(_VERDICT_BY_TYPE)}")
    if not reason_note or not reason_note.strip():
        raise ValueError("reason_note is required and must be non-empty")

    override_id = uuid.uuid4().hex
    overridden_at = overridden_at or datetime.now(tz=timezone.utc)

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO team.planner_overrides
                    (override_id, facility_id, override_type,
                     reason_note, planner_id, overridden_at)
                VALUES
                    (:override_id, :facility_id, :override_type,
                     :reason_note, :planner_id, :overridden_at)
            """),
            {
                "override_id": override_id,
                "facility_id": facility_id,
                "override_type": override_type,
                "reason_note": reason_note,
                "planner_id": planner_id,
                "overridden_at": overridden_at,
            },
        )
    return override_id


# @spec LP-OVR-002, LP-OVR-003, LP-OVR-004
def apply_override(
    engine: Engine,
    override_id: str,
    *,
    recompute_fn: Callable[[Engine, str, str], None],
    capability: str = "maternity",
) -> str:
    """Apply the named override to phantom_verdicts and trigger the
    affected district's score recompute.

    `recompute_fn(engine, district_id, capability) -> None` is invoked inside
    the same transaction as the verdict update. Any exception from it (or
    from the verdict update itself) rolls back the entire operation, leaving
    phantom_verdicts untouched (LP-OVR-004).

    Returns the affected district_id.
    """
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT facility_id, override_type "
                "FROM team.planner_overrides WHERE override_id = :oid"
            ),
            {"oid": override_id},
        ).first()
        if row is None:
            raise LookupError(f"override_id not found: {override_id}")

        facility_id = row.facility_id
        new_verdict = _VERDICT_BY_TYPE[row.override_type]

        district_row = conn.execute(
            text(
                "SELECT district_id FROM operational.facility_district_xref "
                "WHERE facility_id = :fid"
            ),
            {"fid": facility_id},
        ).first()
        if district_row is None:
            raise LookupError(
                f"facility {facility_id} has no entry in facility_district_xref; "
                "engine writer must populate this for override to land cleanly."
            )
        district_id = district_row.district_id

        conn.execute(
            text(
                "UPDATE operational.phantom_verdicts "
                "SET verdict = :verdict, override_id = :oid "
                "WHERE facility_id = :fid"
            ),
            {"verdict": new_verdict, "oid": override_id, "fid": facility_id},
        )

        recompute_fn(engine, district_id, capability)

    return district_id
