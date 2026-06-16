"""App-shell layout — header, tabs, sidebar reserve, footer.

@spec PW-SHELL-001, PW-SHELL-002, PW-SHELL-003, PW-SHELL-004, PW-SHELL-005,
@spec PW-SHELL-006, PW-TAB-001, PW-TAB-002, PW-TAB-003
"""
from __future__ import annotations

TAB_LABELS = ("Map", "Budget Reallocation", "Audit Queue")
FOOTER_TEXT = (
    "Determinism owns the math; AI owns the evidence; "
    "human owns the decision."
)


def render(engine, workspace) -> None:
    """Render the workspace shell + active tab content.

    Lazy-imports streamlit so the package can be loaded by tests without a
    streamlit install.
    """
    import streamlit as st

    from .activation_gate import count_contested, format_activation_gate_label
    from .genie_sidebar import render as render_genie_sidebar
    from .views import (
        audit_view, budget_view, map_view, scenario_panel,
    )
    from phantom_census.lakebase.readers import get_available_capabilities

    # PW-SHELL-002 — capability dropdown populated from desert_scores.
    if "available_capabilities" not in st.session_state:
        st.session_state["available_capabilities"] = (
            get_available_capabilities(engine) or [workspace.capability]
        )
    capabilities = st.session_state["available_capabilities"]

    # PW-SHELL-003 — disable dropdown when only one capability exists.
    capability_disabled = len(capabilities) <= 1
    capability = st.selectbox(
        "Capability", capabilities,
        index=capabilities.index(workspace.capability)
        if workspace.capability in capabilities else 0,
        disabled=capability_disabled,
        key="header_capability",
    )
    workspace.capability = capability

    # PW-SHELL-004 — activation-gate badge.
    contested_count = count_contested(engine, capability=capability)
    st.markdown(format_activation_gate_label(contested_count=contested_count))

    # PW-SHELL-006 — Genie sidebar in left rail.
    render_genie_sidebar(engine, workspace)

    # PW-TAB-001..003 — tabs preserve per-tab state via st.tabs(); shared state
    # lives at the top level of st.session_state.
    tab_map, tab_budget, tab_audit = st.tabs(list(TAB_LABELS))
    with tab_map:
        map_view.render(engine, workspace)
        scenario_panel.render(engine, workspace)
    with tab_budget:
        budget_view.render(engine, workspace)
    with tab_audit:
        audit_view.render(engine, workspace)

    # PW-SHELL-005 — footer tenet.
    st.markdown("---")
    st.caption(FOOTER_TEXT)
