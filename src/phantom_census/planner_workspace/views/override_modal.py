"""Override modal — adjudicator + rescue + AI advisory summary, reason + actions.

@spec PW-OVR-001, PW-OVR-002, PW-OVR-003, PW-OVR-004, PW-OVR-005,
@spec PW-OVR-006, PW-OVR-007
"""
from __future__ import annotations

import json

import streamlit as st
from sqlalchemy import Engine, text

from ..callbacks import submit_override


def render(engine: Engine, workspace) -> None:
    target = st.session_state.get("override_target")
    if not target:
        return

    state = _read_target_state(engine, facility_id=target)
    if state is None:
        st.warning(f"Facility {target} not found in phantom_verdicts.")
        return

    st.subheader(f"Override: {target}")

    # PW-OVR-001 — surface adjudicator_verdict + rescue summary + AI advisory.
    st.markdown(f"Current verdict: **{state['verdict']}**")
    st.markdown(f"Adjudicator output: **{state['adjudicator_verdict']}**")
    rescue_summary = _rescue_summary(state.get("rescue_applied"))
    st.markdown(f"Layer A rescue: {rescue_summary}")

    if state["verdict"] == "contested":
        rec = state.get("ai_recommendation")
        if rec:
            st.markdown(
                f"AI advisory: **{rec.get('recommendation', '?')}** "
                f"(confidence: {rec.get('confidence', '?')})"
            )
            reasoning = rec.get("reasoning")
            if reasoning:
                st.markdown(f"_{reasoning}_")
        else:
            # PW-OVR-007 — Override panel never invokes FMA.
            st.info(
                "AI advisory: not yet computed (expand the row to fetch)."
            )
    else:
        st.markdown("AI advisory: n/a (verdict is not contested)")

    reason = st.text_area("Reason note (required)", key=f"ovr-reason-{target}")
    enabled = bool(reason and reason.strip())

    # PW-OVR-002 — buttons disabled until reason is filled.
    cols = st.columns(3)
    if cols[0].button("Force Real", disabled=not enabled,
                      key=f"ovr-real-{target}"):
        _commit(engine, workspace, target, "force-real", reason)
    if cols[1].button("Force Phantom", disabled=not enabled,
                      key=f"ovr-phantom-{target}"):
        _commit(engine, workspace, target, "force-phantom", reason)
    if cols[2].button("Cancel", key=f"ovr-cancel-{target}"):
        st.session_state.pop("override_target", None)


def _read_target_state(engine: Engine, facility_id: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT facility_id, adjudicator_verdict, verdict,
                   rescue_applied, ai_recommendation, override_id
            FROM operational.phantom_verdicts
            WHERE facility_id = :fid
        """), {"fid": facility_id}).mappings().first()
    if row is None:
        return None
    return dict(row)


def _rescue_summary(rescue_applied) -> str:
    if rescue_applied is None:
        return "none"
    if isinstance(rescue_applied, str):
        try:
            rescue_applied = json.loads(rescue_applied)
        except Exception:
            return rescue_applied
    if isinstance(rescue_applied, dict):
        signals = rescue_applied.get("signals", []) or []
        names = [s.get("signal") for s in signals if isinstance(s, dict)]
        return ", ".join(n for n in names if n) or "none"
    return str(rescue_applied)


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
    except Exception as exc:
        workspace.last_error = f"Override failed: {exc}"
        return
    workspace.override_set.append(override_id)
    workspace.last_error = None
    st.session_state.pop("override_target", None)
    # PW-OVR-006 — flag the budget + audit tabs as stale so a tab switch
    # rebuilds from the post-override desert_scores + phantom_verdicts.
    st.session_state["budget_dirty"] = True
    st.session_state["audit_dirty"] = True
    # PW-OVR-004 — verdict badge update message.
    st.toast(f"Override saved: {kind} (overridden, note: {reason[:40]})")
