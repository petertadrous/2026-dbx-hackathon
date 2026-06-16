"""Top-movers panel — surfaces the biggest rank shifts when phantoms are subtracted.

This is the canonical demo storytelling slot: when the HLD success metric says
"BEED rank 10 → 2", that comparison lands HERE. Without this panel the
choropleth color shift is the only visual cue; with it, the planner sees the
literal rank delta on the side.

@spec DS-RANK-001, DS-RANK-002, DS-RANK-003
"""
from __future__ import annotations

import streamlit as st
from sqlalchemy import Engine

from phantom_census.desert_scoring.tiles import build_rank_table
from phantom_census.lakebase.readers import get_desert_scores

TOP_N = 5


def render(engine: Engine, workspace) -> None:
    scores = get_desert_scores(engine, capability=workspace.capability)
    if scores.empty:
        return

    rank = build_rank_table(scores, active="adjusted")
    # Districts whose adjusted rank is meaningfully better (more toward #1) than
    # their raw rank are the ones the phantom subtraction reveals.
    movers = (
        rank[rank["rank_delta"] != 0]
        .reindex(rank["rank_delta"].abs().sort_values(ascending=False).index)
        .head(TOP_N)
    )
    if movers.empty:
        return

    st.subheader("Top movers (rank shift)")
    st.caption(
        "Largest absolute rank deltas between Raw and Adjusted views. "
        "Positive Δ = climbs toward the worst-desert top."
    )
    for _, m in movers.iterrows():
        delta = int(m["rank_delta"])
        arrow = "▲" if delta > 0 else "▼"
        cols = st.columns([3, 1, 1, 1])
        cols[0].markdown(f"**{m['district_name']}**, {m['state_name']}")
        cols[1].markdown(f"Raw #{int(m['raw_rank'])}")
        cols[2].markdown(f"Adj #{int(m['adjusted_rank'])}")
        cols[3].markdown(f"{arrow} **{abs(delta)}**")
