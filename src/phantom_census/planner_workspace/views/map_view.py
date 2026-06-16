"""Map view — capability picker, raw/adjusted toggle, choropleth, header counter.

@spec PW-MAP-001, PW-MAP-002, PW-MAP-003, PW-MAP-004, PW-MAP-005, PW-MAP-006, PW-MAP-007
"""
from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components
from sqlalchemy import Engine

from phantom_census.desert_scoring.tiles import (
    phantom_counter,
    token_usage_indicator,
)
from phantom_census.lakebase.readers import get_desert_scores, get_tile_html

from ..css import base_styles, layer_visibility_block

SUPPORTED_CAPABILITIES = ("maternity",)


def render(engine: Engine, workspace) -> None:
    st.markdown(base_styles(), unsafe_allow_html=True)

    header_cols = st.columns([2, 2, 2, 2])

    # @spec PW-MAP-002
    with header_cols[0]:
        capability = st.selectbox(
            "Capability",
            SUPPORTED_CAPABILITIES,
            index=SUPPORTED_CAPABILITIES.index(workspace.capability)
            if workspace.capability in SUPPORTED_CAPABILITIES else 0,
        )
        workspace.capability = capability

    # @spec PW-MAP-003
    with header_cols[1]:
        view = st.radio(
            "View",
            ("raw", "adjusted"),
            index=0 if workspace.view == "raw" else 1,
            horizontal=True,
            format_func=lambda s: "Raw" if s == "raw" else "Adjusted",
        )
        workspace.view = view

    # @spec PW-MAP-005, PW-MAP-007
    scores = get_desert_scores(engine, capability=workspace.capability)
    phantom_total = phantom_counter(scores) if not scores.empty else 0
    with header_cols[2]:
        st.markdown(
            f"<div class='pc-counter'>Phantoms removed: "
            f"<strong>{phantom_total if view == 'adjusted' else 0}</strong></div>",
            unsafe_allow_html=True,
        )

    # @spec PW-MAP-006
    with header_cols[3]:
        st.markdown(f"`{token_usage_indicator()}`")

    # @spec PW-MAP-001, PW-MAP-004
    raw_html = get_tile_html(engine, capability=workspace.capability,
                             layer_type="raw") or ""
    adjusted_html = get_tile_html(engine, capability=workspace.capability,
                                  layer_type="adjusted") or raw_html

    combined = (
        f"{layer_visibility_block(view)}"
        f"<div id='pc-layer-raw' class='pc-tile-layer'>{raw_html}</div>"
        f"<div id='pc-layer-adjusted' class='pc-tile-layer'>{adjusted_html}</div>"
    )
    components.html(combined, height=600, scrolling=False)
