"""Override modal — required reason note, force-real / force-phantom buttons.

@spec PW-OVR-001, PW-OVR-002, PW-OVR-003, PW-OVR-004, PW-OVR-005
"""
from __future__ import annotations

import streamlit as st
from sqlalchemy import Engine

from ..callbacks import submit_override


def render(engine: Engine, workspace) -> None:
    target = st.session_state.get("override_target")
    if not target:
        return

    st.subheader(f"Override: {target}")
    reason = st.text_area("Reason note (required)", key=f"ovr-reason-{target}")
    enabled = bool(reason and reason.strip())
    # @spec PW-OVR-002
    cols = st.columns(2)
    if cols[0].button("Force Real", disabled=not enabled,
                      key=f"ovr-real-{target}"):
        _commit(engine, workspace, target, "force-real", reason)
    if cols[1].button("Force Phantom", disabled=not enabled,
                      key=f"ovr-phantom-{target}"):
        _commit(engine, workspace, target, "force-phantom", reason)


def _commit(engine, workspace, target: str, kind: str, reason: str) -> None:
    try:
        override_id = submit_override(
            engine,
            facility_id=target,
            override_type=kind,
            reason_note=reason,
            planner_id=st.session_state["planner_id"],
            capability=workspace.capability,
        )
    except Exception as exc:  # @spec PW-OVR-005 surfaces error to side panel
        workspace.last_error = f"Override failed: {exc}"
        return
    workspace.override_set.append(override_id)
    workspace.last_error = None
    st.session_state.pop("override_target", None)
    st.toast(f"Override saved: {kind}")
