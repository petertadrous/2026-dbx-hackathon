"""Phantom Census — planner workspace (Streamlit app)."""
from __future__ import annotations


def main() -> None:
    """Streamlit app entry. Lazy-imports streamlit so the package can be loaded
    by tests without a streamlit install.

    The shell module owns the tabbed layout, capability dropdown, activation-
    gate badge, footer, and sidebar reserve (PW-SHELL-001..006). Tab content
    is dispatched per-view by shell.render.
    """
    import streamlit as st
    from sqlalchemy import Engine

    from phantom_census.lakebase.engine import get_engine

    from .fma_adapter import build_ai_evidence_adapter, build_genie_sql_adapter
    from .session import init_session_state, resolve_planner_id
    from . import shell

    @st.cache_resource
    def _engine() -> Engine:
        # Cached across Streamlit reruns to avoid SQLAlchemy pool churn.
        return get_engine()

    st.set_page_config(
        page_title="Phantom Census",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    try:
        headers = dict(st.context.headers) if hasattr(st, "context") else {}
    except Exception:
        headers = {}
    planner_id = resolve_planner_id(headers)

    engine = _engine()
    workspace = init_session_state(st.session_state, planner_id)

    # FMA adapters — env-var-driven; default raises so the existence-engine's
    # template-fallback path (EE-AI-009) fires and the Genie sidebar shows
    # "endpoint not configured for local dev".
    if "ai_query_adapter" not in st.session_state:
        st.session_state["ai_query_adapter"] = build_ai_evidence_adapter()
    if "genie_query_adapter" not in st.session_state:
        st.session_state["genie_query_adapter"] = build_genie_sql_adapter()

    last_error = workspace.last_error
    workspace.last_error = None
    if last_error:
        st.error(last_error)

    shell.render(engine, workspace)
