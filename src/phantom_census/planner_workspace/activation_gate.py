"""Activation-gate header badge — PW-SHELL-004.

The header displays a one-line activation gate metric:
`Activation gate: N contested · est. cost ≤ $X` where N is the count of
contested verdicts in scope and X is N × $0.005.
"""
from __future__ import annotations

from sqlalchemy import Engine, text

# Per-FMA call cost estimate (USD). Used by the activation-gate badge as the
# ceiling estimate; actual session spend tracks separately.
PER_FMA_COST_USD = 0.005


# @spec PW-SHELL-004
def format_activation_gate_label(*, contested_count: int) -> str:
    cost = contested_count * PER_FMA_COST_USD
    return f"Activation gate: {contested_count} contested · est. cost ≤ ${cost:.2f}"


# @spec PW-SHELL-004
def count_contested(engine: Engine, capability: str) -> int:
    """SELECT COUNT(*) FROM phantom_verdicts JOIN xref WHERE verdict = 'contested'
    AND the facility is in scope of the active capability."""
    with engine.connect() as conn:
        return int(conn.execute(text("""
            SELECT COUNT(DISTINCT pv.facility_id)
            FROM operational.phantom_verdicts pv
            JOIN operational.facility_capabilities fc USING (facility_id)
            WHERE pv.verdict = 'contested'
              AND fc.capability = :capability
        """), {"capability": capability}).scalar_one())
