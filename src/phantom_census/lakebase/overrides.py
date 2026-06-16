"""Override write path.

@spec LP-OVR-001, LP-OVR-002, LP-OVR-003, LP-OVR-004, LP-OVR-005, LP-OVR-006
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from sqlalchemy import Connection, Engine, text

OverrideType = Literal["force-real", "force-phantom"]

# Recompute callback signature accepts `facility_id` so DS-MULTICAP-001 can
# enumerate the facility's capabilities. Older callers that pass only
# (conn, district_id, capability) still work because the parameter is keyword.
RecomputeFn = Callable[..., Any]

# LP-SCHEMA-VERDICT-002: planner-override verdict enum values.
_PLANNER_VERDICT_BY_TYPE: dict[str, str] = {
    "force-real": "force-real-planner",
    "force-phantom": "force-phantom-planner",
}


def _validate(override_type: str, reason_note: str) -> None:
    if override_type not in _PLANNER_VERDICT_BY_TYPE:
        raise ValueError(f"override_type must be one of {set(_PLANNER_VERDICT_BY_TYPE)}")
    if not reason_note or not reason_note.strip():
        raise ValueError("reason_note is required and must be non-empty")


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

    Audit-trail-only helper — does not touch phantom_verdicts. For the planner
    workflow that commits an audit row AND mutates the verdict atomically, use
    ``submit_override``.
    """
    _validate(override_type, reason_note)
    override_id = uuid.uuid4().hex
    overridden_at = overridden_at or datetime.now(tz=timezone.utc)
    with engine.begin() as conn:
        _insert_audit_row(
            conn, override_id=override_id,
            facility_id=facility_id, override_type=override_type,
            reason_note=reason_note, planner_id=planner_id,
            overridden_at=overridden_at,
        )
    return override_id


# @spec LP-OVR-001, LP-OVR-002, LP-OVR-003, LP-OVR-004, LP-OVR-005, LP-OVR-006
def submit_override(
    engine: Engine,
    *,
    facility_id: str,
    override_type: OverrideType,
    reason_note: str,
    planner_id: str,
    capability: str = "maternity",
    recompute_fn: RecomputeFn,
    overridden_at: datetime | None = None,
) -> tuple[str, str]:
    """Append an audit row AND apply the override in one transaction.

    Returns ``(override_id, affected_district_id)``. If ``recompute_fn`` raises
    (or any earlier step fails) every write — audit row, verdict update, and
    score recompute — rolls back together (LP-OVR-005).

    Per LP-OVR-002, the verdict is set to the planner enum values
    ``force-real-planner`` or ``force-phantom-planner`` (LP-SCHEMA-VERDICT-002).
    Per LP-OVR-003, the UPDATE writes only ``verdict`` and ``override_id``,
    preserving ``adjudicator_verdict``, ``rescue_applied``,
    ``ai_recommendation``, and ``ai_recommendation_evidence_state`` unchanged.
    Per LP-OVR-006, the audit table is append-only — repeat overrides on the
    same ``facility_id`` produce new rows; only ``phantom_verdicts.override_id``
    advances to the latest row.
    """
    _validate(override_type, reason_note)
    override_id = uuid.uuid4().hex
    overridden_at = overridden_at or datetime.now(tz=timezone.utc)

    with engine.begin() as conn:
        _insert_audit_row(
            conn, override_id=override_id,
            facility_id=facility_id, override_type=override_type,
            reason_note=reason_note, planner_id=planner_id,
            overridden_at=overridden_at,
        )

        district_id = _lookup_district(conn, facility_id)
        new_verdict = _PLANNER_VERDICT_BY_TYPE[override_type]

        # @spec LP-OVR-003 — UPDATE writes only the planner-mutable columns.
        # adjudicator_verdict, rescue_applied, ai_recommendation, and
        # ai_recommendation_evidence_state are NOT in the SET list.
        conn.execute(
            text(
                "UPDATE operational.phantom_verdicts "
                "SET verdict = :verdict, override_id = :oid "
                "WHERE facility_id = :fid"
            ),
            {"verdict": new_verdict, "oid": override_id, "fid": facility_id},
        )

        recompute_fn(conn, district_id, capability, facility_id=facility_id)

    return override_id, district_id


# @spec LP-OVR-002, LP-OVR-003, LP-OVR-004
def apply_override(
    engine: Engine,
    override_id: str,
    *,
    recompute_fn: RecomputeFn,
    capability: str = "maternity",
) -> str:
    """Apply a pre-existing audit row to phantom_verdicts in one transaction.

    Use when the audit row was written separately. For the planner UI flow
    prefer ``submit_override``.
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
        new_verdict = _PLANNER_VERDICT_BY_TYPE[row.override_type]
        district_id = _lookup_district(conn, facility_id)

        conn.execute(
            text(
                "UPDATE operational.phantom_verdicts "
                "SET verdict = :verdict, override_id = :oid "
                "WHERE facility_id = :fid"
            ),
            {"verdict": new_verdict, "oid": override_id, "fid": facility_id},
        )

        recompute_fn(conn, district_id, capability, facility_id=facility_id)

    return district_id


def _insert_audit_row(conn: Connection, **values) -> None:
    conn.execute(
        text("""
            INSERT INTO team.planner_overrides
                (override_id, facility_id, override_type,
                 reason_note, planner_id, overridden_at)
            VALUES
                (:override_id, :facility_id, :override_type,
                 :reason_note, :planner_id, :overridden_at)
        """),
        values,
    )


def _lookup_district(conn: Connection, facility_id: str) -> str:
    row = conn.execute(
        text(
            "SELECT district_id FROM operational.facility_district_xref "
            "WHERE facility_id = :fid"
        ),
        {"fid": facility_id},
    ).first()
    if row is None:
        raise LookupError(
            f"facility {facility_id} has no entry in facility_district_xref; "
            "the engine writer must populate this before any override lands."
        )
    return row.district_id
