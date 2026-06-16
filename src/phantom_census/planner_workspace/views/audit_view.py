"""Audit Queue view — top-50 inspector worksheet + PDF export.

@spec PW-AUDIT-001, PW-AUDIT-002, PW-AUDIT-003, PW-AUDIT-004, PW-AUDIT-005
"""
from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import Engine, text

from ..audit import build_audit_queue, render_inspector_worksheet_pdf


def render(engine: Engine, workspace) -> None:
    st.subheader("Audit Queue")
    capability = workspace.capability
    phantoms = _read_phantoms(engine, capability=capability)
    leverage = _read_district_leverage(engine, capability=capability)

    if phantoms.empty:
        st.info("No phantom-verdicted facilities for this capability.")
        return

    queue = build_audit_queue(phantoms, leverage)

    st.markdown(
        f"Top-{len(queue)} facilities to audit — capability: **{capability}** · "
        "ordered by leverage = burden × population × phantom density"
    )
    st.dataframe(queue, use_container_width=True)

    # PW-AUDIT-003 — PDF export.
    pdf_bytes = render_inspector_worksheet_pdf(queue)
    last_exported = st.session_state.get("audit_last_exported")
    label = "Export inspector worksheet PDF"
    if last_exported:
        label += f"  (last exported: {last_exported})"
    st.download_button(
        label, data=pdf_bytes,
        file_name="inspector_worksheet.pdf", mime="application/pdf",
        key="audit_export",
    )


def _read_phantoms(engine: Engine, capability: str) -> pd.DataFrame:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT pv.facility_id, pv.facility_id AS facility_name,
                   x.district_id, ds.district_name,
                   '' AS pincode, NULL AS latitude, NULL AS longitude,
                   pv.test_outcome_vector, pv.verdict
            FROM operational.phantom_verdicts pv
            JOIN operational.facility_district_xref x USING (facility_id)
            JOIN operational.facility_capabilities fc USING (facility_id)
            JOIN operational.desert_scores ds
              ON ds.district_id = x.district_id AND ds.capability = :capability
            WHERE pv.verdict = 'phantom'
              AND fc.capability = :capability
        """), {"capability": capability}).mappings().all()
    return pd.DataFrame(rows)


def _read_district_leverage(engine: Engine, capability: str) -> pd.DataFrame:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT district_id, burden_weight,
                   verified_facility_count, phantom_count,
                   max_density, 1.0 AS area_km2
            FROM operational.desert_scores
            WHERE capability = :capability
        """), {"capability": capability}).mappings().all()
    return pd.DataFrame(rows)
