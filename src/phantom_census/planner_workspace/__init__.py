"""Phantom Census — planner workspace (Streamlit app)."""
from __future__ import annotations


def main() -> None:
    """Streamlit app entry. Lazy-imports streamlit so the package can be loaded
    by tests without a streamlit install."""
    import streamlit as st
    from sqlalchemy import Engine

    from phantom_census.lakebase.engine import get_engine

    from .session import init_session_state, resolve_planner_id
    from .views import (
        map_view, override_modal, rank_movers, scenario_panel, side_panel,
    )

    @st.cache_resource
    def _engine() -> Engine:
        # @spec PW (engine reuse) — caching across Streamlit reruns avoids
        # SQLAlchemy connection-pool churn on every interaction.
        return get_engine()

    st.set_page_config(
        page_title="Phantom Census",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    # @spec PW-OVR-003, PW-SCEN-001 — planner identity in production comes from
    # the Apps-injected `X-Forwarded-Email` header (st.context.headers); the env
    # var and local-dev paths are fallbacks.
    try:
        headers = dict(st.context.headers) if hasattr(st, "context") else {}
    except Exception:
        headers = {}
    planner_id = resolve_planner_id(headers)

    engine = _engine()
    workspace = init_session_state(st.session_state, planner_id)

    last_error = workspace.last_error
    workspace.last_error = None  # display once; siblings re-set if they fail
    if last_error:
        st.error(last_error)

    map_col, panel_col = st.columns([0.6, 0.4])
    with map_col:
        map_view.render(engine, workspace)
        rank_movers.render(engine, workspace)
    with panel_col:
        side_panel.render(engine, workspace)
        override_modal.render(engine, workspace)
        scenario_panel.render(engine, workspace)
