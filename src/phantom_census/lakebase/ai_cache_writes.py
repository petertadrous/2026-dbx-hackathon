"""AI Evidence Layer persistence path.

@spec LP-AI-CACHE-001, LP-AI-CACHE-002, LP-AI-CACHE-003, LP-AI-CACHE-004,
@spec LP-AI-CACHE-005
"""
from __future__ import annotations

import json

from sqlalchemy import Engine, text


# @spec LP-AI-CACHE-001, LP-AI-CACHE-003, LP-AI-CACHE-004, LP-AI-CACHE-005
def persist_ai_recommendation(
    engine: Engine,
    *,
    facility_id: str,
    recommendation: dict,
    evidence_state: str,
) -> bool:
    """UPDATE phantom_verdicts.ai_recommendation + ai_recommendation_evidence_state.

    LP-AI-CACHE-001: write JSONB recommendation and sha256-hex evidence_state
    in a single statement.

    LP-AI-CACHE-003: this path does NOT modify ``verdict``,
    ``adjudicator_verdict``, ``rescue_applied``, ``test_outcome_vector``, or
    ``override_id`` — only the two AI cache columns.

    LP-AI-CACHE-004: plain UPDATE, last-write-wins. No advisory lock; the
    race-cost of two concurrent FMA invocations is ~$0.05 per collision and
    the two recommendations are substantively equivalent given identical
    evidence.

    LP-AI-CACHE-005: the UPDATE is guarded by ``override_id IS NULL`` — if a
    planner override has landed between the FMA invocation and this write,
    the UPDATE matches zero rows and the recommendation is discarded. Returns
    ``True`` when the write succeeded; ``False`` when the override guard
    suppressed it.
    """
    payload = json.dumps(recommendation)
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE operational.phantom_verdicts
                SET ai_recommendation = CAST(:rec AS JSONB),
                    ai_recommendation_evidence_state = :state
                WHERE facility_id = :fid
                  AND override_id IS NULL
            """),
            {"rec": payload, "state": evidence_state, "fid": facility_id},
        )
    return (result.rowcount or 0) > 0
