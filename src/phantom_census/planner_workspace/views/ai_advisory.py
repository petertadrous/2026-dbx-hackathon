"""AI Advisory block view.

@spec PW-AI-001, PW-AI-002, PW-AI-003, PW-AI-004, PW-AI-005

The block is rendered inline within a contested facility's expanded side-panel
row. The render-decision logic (when to render, whether to mark historical,
whether to flag template-fallback) lives in
`planner_workspace.ai_advisory_render`; this module owns the visual layer
only.
"""
from __future__ import annotations

import streamlit as st
from sqlalchemy import Engine

from ..ai_advisory_render import decide_advisory_render


def render(engine: Engine, workspace) -> None:
    """No-op top-level entry; the AI Advisory block renders inline per row.

    Kept for smoke-test parity (`test_ai_advisory_module_exposes_render`)
    with the other view modules. The active call site is
    `side_panel.render`'s per-row expand handler which calls
    `render_block(rendered)` below.
    """
    return


def render_block(rendered: dict) -> None:
    """Render one AI Advisory block.

    `rendered` is the dict returned by
    `planner_workspace.ai_advisory_render.decide_advisory_render`.
    """
    payload = rendered.get("payload") or {}
    is_historical = rendered.get("mark") == "historical-advisory"

    header_bits = ["**AI Advisory**"]
    confidence = payload.get("confidence", "low")
    if rendered.get("template_fallback"):
        # PW-AI-002 — append marker.
        header_bits.append(f"confidence: {confidence} (template fallback)")
    else:
        header_bits.append(f"confidence: {confidence}")
    if is_historical:
        # PW-AI-003 — historical advisory marker.
        header_bits.append("(historical advisory)")
    st.markdown(" — ".join(header_bits))
    st.markdown(f"Recommendation: **{payload.get('recommendation', '?')}**")
    reasoning = payload.get("reasoning", "")
    if reasoning:
        st.markdown(f"_{reasoning}_")
    cited = payload.get("cited_evidence_rows") or []
    if cited:
        st.caption(f"Cited rows: {', '.join(str(c) for c in cited)}")
