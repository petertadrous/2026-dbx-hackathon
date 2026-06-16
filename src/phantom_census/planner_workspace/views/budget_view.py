"""Budget Reallocation view — before/after pies, recommendation table, CSV export.

@spec PW-BUDGET-001, PW-BUDGET-002, PW-BUDGET-003, PW-BUDGET-004,
@spec PW-BUDGET-005, PW-BUDGET-006, PW-BUDGET-007
"""
from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import Engine, text

from phantom_census.lakebase.readers import get_desert_scores

from ..budget import compute_recommended_allocation, serialize_recommendation_csv


def render(engine: Engine, workspace) -> None:
    st.subheader("Budget Reallocation")
    capability = workspace.capability
    allocations = _read_allocations(engine, capability=capability)
    scores = get_desert_scores(engine, capability=capability)

    if allocations.empty:
        st.info(
            f"No budget allocations loaded for capability '{capability}'. "
            "Run the budget-allocations CSV loader at project setup."
        )
        return
    if scores.empty:
        st.info("No desert scores available; the recommendation cannot be computed.")
        return

    rec = compute_recommended_allocation(scores, allocations)

    cols = st.columns(2)
    # PW-BUDGET-001 — Before / Recommended pies.
    with cols[0]:
        st.markdown("**Before**")
        st.bar_chart(allocations.set_index("district_id")["allocated_inr"])
    with cols[1]:
        st.markdown("**Recommended**")
        st.bar_chart(rec.set_index("district_id")["recommended_inr"])

    # PW-BUDGET-003 — recommendation table.
    st.markdown("#### Recommended shifts")
    st.dataframe(rec, use_container_width=True)

    # PW-BUDGET-004 — CSV export.
    csv_blob = serialize_recommendation_csv(rec)
    last_exported = st.session_state.get("budget_last_exported")
    label = "Export revised allocation CSV"
    if last_exported:
        label += f"  (last exported: {last_exported})"
    st.download_button(
        label, data=csv_blob,
        file_name="revised_allocation.csv", mime="text/csv",
        key="budget_export",
    )


def _read_allocations(engine: Engine, capability: str) -> pd.DataFrame:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT district_id, state_name, capability, quarter, allocated_inr
            FROM team.budget_allocations
            WHERE capability = :capability
            ORDER BY allocated_inr DESC
        """), {"capability": capability}).mappings().all()
    return pd.DataFrame(rows)
