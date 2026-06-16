"""Scenario save / restore.

@spec PW-SCEN-001, PW-SCEN-002, PW-SCEN-003, PW-SCEN-004
"""
from __future__ import annotations

import streamlit as st
from sqlalchemy import Engine

from phantom_census.lakebase.readers import get_saved_scenarios

from ..callbacks import restore, submit_scenario_save


def render(engine: Engine, workspace) -> None:
    st.subheader("Scenarios")
    # @spec PW-SCEN-001
    with st.expander("Save current session", expanded=False):
        name = st.text_input("Scenario name")
        notes = st.text_area("Notes")
        if st.button("Save scenario", disabled=not name.strip()):
            try:
                submit_scenario_save(
                    engine,
                    scenario_name=name,
                    capability=workspace.capability,
                    region_filter=None,
                    override_ids=list(workspace.override_set),
                    planner_notes=notes,
                    planner_id=st.session_state["planner_id"],
                )
                st.toast("Scenario saved")
            except Exception as exc:
                workspace.last_error = f"Scenario save failed: {exc}"

    # @spec PW-SCEN-002, PW-SCEN-003, PW-SCEN-004
    saved = get_saved_scenarios(engine, planner_id=st.session_state["planner_id"])
    if saved.empty:
        st.caption("No saved scenarios yet.")
        return
    choice = st.selectbox(
        "Restore", ["—"] + saved["scenario_name"].tolist(),
        key="restore-pick",
    )
    if choice and choice != "—":
        sid = saved[saved["scenario_name"] == choice].iloc[0]["scenario_id"]
        if st.button("Restore selected scenario"):
            try:
                restore(engine, scenario_id=sid)
                st.toast("Scenario restored")
            except Exception as exc:
                workspace.last_error = f"Restore failed: {exc}"
