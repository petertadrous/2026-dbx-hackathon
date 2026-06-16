"""Defender Layer A persistence path.

@spec LP-RESCUE-001, LP-RESCUE-002
"""
from __future__ import annotations

import json

from sqlalchemy import Engine, text


# @spec LP-RESCUE-001, LP-RESCUE-002
def apply_layer_a_rescue(
    engine: Engine,
    *,
    facility_id: str,
    rescue_applied: dict,
) -> None:
    """LP-RESCUE-001: patch verdict from `phantom` to `contested` and write the
    rescue trace to ``phantom_verdicts.rescue_applied`` JSONB.

    ``adjudicator_verdict`` is preserved unchanged (per LP-RESCUE-001 and the
    EE-LAYER-A-005 contract). The WHERE clause restricts the UPDATE to
    facilities the Adjudicator marked phantom, satisfying EE-LAYER-A-006's
    "never upgrade to real" guarantee.

    LP-RESCUE-002: this path does NOT write rows to
    ``operational.facility_existence_tests`` — the rescue trace lives only in
    the JSONB column.
    """
    payload = json.dumps(rescue_applied)
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE operational.phantom_verdicts
                SET verdict = 'contested',
                    rescue_applied = CAST(:rescue AS JSONB)
                WHERE facility_id = :fid
                  AND adjudicator_verdict = 'phantom'
            """),
            {"rescue": payload, "fid": facility_id},
        )
