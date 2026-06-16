"""Genie NL sidebar — read-only SQL allow-list over operational/team tables.

@spec PW-GENIE-001, PW-GENIE-002, PW-GENIE-003, PW-GENIE-004

For the hackathon scope, the sidebar is a stub: it exposes the allow-list
(via `planner_workspace.genie_scope`), accepts a chat input, and either runs
the SQL (when it passes the allow-list) or refuses it. A real Databricks Genie
endpoint can be swapped in by injecting an adapter into
`st.session_state['genie_query_adapter']`.
"""
from __future__ import annotations

import streamlit as st
from sqlalchemy import Engine, text

from ..genie_scope import GENIE_ALLOWED_TABLES, is_genie_sql_allowed


def render(engine: Engine, workspace) -> None:
    """PW-SHELL-006 / PW-GENIE-004 — render the Genie sidebar in the left rail."""
    with st.sidebar:
        st.subheader("Genie")
        st.caption(
            "Read-only NL → SQL over operational + team tables. "
            "Allowed: " + ", ".join(sorted(GENIE_ALLOWED_TABLES))
        )
        question = st.chat_input("Ask a question…", key="genie_chat_input")
        if not question:
            return

        adapter = st.session_state.get("genie_query_adapter")
        if adapter is None:
            st.info(
                "Genie endpoint not configured for local dev. "
                "Inject `st.session_state['genie_query_adapter']` to enable."
            )
            return

        sql = adapter(question)
        if not isinstance(sql, str) or not is_genie_sql_allowed(sql):
            st.error("Generated SQL was outside the allow-list and was refused.")
            st.code(sql or "(no SQL produced)", language="sql")
            return

        with engine.connect() as conn:
            try:
                rows = conn.execute(text(sql)).mappings().all()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Query failed: {exc}")
                return
        if not rows:
            st.write("(no rows)")
        else:
            st.dataframe(rows, use_container_width=True)
