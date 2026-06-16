"""Phantom Census — planner workspace (Streamlit app)."""
from __future__ import annotations


def main() -> None:
    """Streamlit app entry. Lazy-imports streamlit so the package can be loaded
    by tests without a streamlit install."""
    import streamlit as st
    from sqlalchemy import Engine

    from phantom_census.lakebase.engine import get_engine

    from .session import init_session_state, resolve_planner_id
    from .views import map_view, override_modal, scenario_panel, side_panel

    st.set_page_config(
        page_title="Phantom Census",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    planner_id = resolve_planner_id()
    engine: Engine = get_engine()
    workspace = init_session_state(st.session_state, planner_id)

    if workspace.last_error:
        st.error(workspace.last_error)

    map_col, panel_col = st.columns([0.6, 0.4])
    with map_col:
        map_view.render(engine, workspace)
    with panel_col:
        side_panel.render(engine, workspace)
        override_modal.render(engine, workspace)
        scenario_panel.render(engine, workspace)
