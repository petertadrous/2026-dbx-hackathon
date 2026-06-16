"""District side panel — selection metadata + phantom list + evidence expanders.

@spec PW-PANEL-001, PW-PANEL-002, PW-PANEL-003, PW-PANEL-004
"""
from __future__ import annotations

import streamlit as st
from sqlalchemy import Engine

from phantom_census.desert_scoring.tiles import build_rank_table
from phantom_census.lakebase.readers import (
    get_desert_scores,
    get_district_phantoms,
    get_facility_tests,
)

PHANTOM_LIMIT = 5


def render(engine: Engine, workspace) -> None:
    st.subheader("District")
    district_options = ["—"]
    scores = get_desert_scores(engine, capability=workspace.capability)
    if not scores.empty:
        district_options += sorted(scores["district_id"].unique().tolist())
    selection = st.selectbox(
        "Select a district",
        district_options,
        index=district_options.index(workspace.selected_district)
        if workspace.selected_district in district_options else 0,
    )
    workspace.selected_district = None if selection == "—" else selection
    if workspace.selected_district is None:
        st.info("Pick a district to see its desert score and phantom list.")
        return

    # @spec PW-PANEL-001
    row = scores[scores["district_id"] == workspace.selected_district].iloc[0]
    rank = build_rank_table(scores, active=workspace.view)
    rank_row = rank[rank["district_id"] == workspace.selected_district].iloc[0]
    st.markdown(f"### {row['district_name']}, {row['state_name']}")
    st.markdown(
        f"Raw score: **{row['raw_desert_score']:.2f}** · "
        f"Adjusted score: **{row['adjusted_desert_score']:.2f}**"
    )
    st.markdown(
        f"Raw rank: **{int(rank_row['raw_rank'])}** · "
        f"Adjusted rank: **{int(rank_row['adjusted_rank'])}** · "
        f"Δ: **{int(rank_row['rank_delta'])}**"
    )

    # @spec PW-PANEL-002
    phantoms = get_district_phantoms(
        engine, district_id=workspace.selected_district, limit=PHANTOM_LIMIT,
    )
    if phantoms.empty:
        st.info("No phantom-verdicted facilities in this district.")
        return

    st.markdown("#### Phantom facilities")
    for _, p in phantoms.iterrows():
        with st.container():
            cols = st.columns([3, 1])
            cols[0].markdown(
                f"**{p['facility_id']}** — {p.get('reason') or 'phantom'}"
            )
            if cols[1].button("Override", key=f"ovr-{p['facility_id']}"):
                st.session_state["override_target"] = p["facility_id"]
            # @spec PW-PANEL-003
            with st.expander("Evidence", expanded=False):
                tests = get_facility_tests(engine, facility_id=p["facility_id"])
                if tests.empty:
                    st.write("No test rows on file.")
                else:
                    st.dataframe(tests, use_container_width=True)
