"""District side panel — selection metadata + phantom-or-contested list + AI advisory.

@spec PW-PANEL-001, PW-PANEL-002, PW-PANEL-003, PW-PANEL-004, PW-PANEL-005
"""
from __future__ import annotations

import streamlit as st
from sqlalchemy import Engine

from phantom_census.desert_scoring.ranking import build_rank_table
from phantom_census.lakebase.readers import (
    get_desert_scores,
    get_district_phantoms,
    get_facility_tests,
)

from ..ai_advisory_render import decide_advisory_render
from .ai_advisory import render_block as render_ai_advisory_block

PHANTOM_LIMIT = 5


def _default_ai_query(**_kwargs):
    """Default AI query adapter — raises so the template fallback fires.

    Swap in a real Foundation Model adapter via DI for production runs.
    """
    raise NotImplementedError("AI query adapter not configured for local dev")


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

    # PW-PANEL-001
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

    # PW-PANEL-002 — phantom OR contested; leverage-ranked; collapsed by default.
    rows = get_district_phantoms(
        engine, district_id=workspace.selected_district, limit=PHANTOM_LIMIT,
    )
    if rows.empty:
        st.info("No phantom-or-contested facilities in this district.")
        return

    st.markdown("#### Phantom or contested facilities (leverage-ranked)")
    ai_query = st.session_state.get("ai_query_adapter", _default_ai_query)
    for _, p in rows.iterrows():
        with st.container():
            cols = st.columns([3, 1])
            cols[0].markdown(
                f"**{p['facility_id']}** — {p.get('verdict')} "
                f"(adjudicator: {p.get('adjudicator_verdict')})"
            )
            if cols[1].button("Override", key=f"ovr-{p['facility_id']}"):
                st.session_state["override_target"] = p["facility_id"]

            # PW-PANEL-002 — collapsed by default; PW-PANEL-005 — AI gate is
            # row-expand of a contested facility, not panel open.
            with st.expander("Evidence", expanded=False):
                tests = get_facility_tests(engine, facility_id=p["facility_id"])
                if tests.empty:
                    st.write("No test rows on file.")
                else:
                    st.dataframe(tests, use_container_width=True)

                # PW-PANEL-005 — gate AI Evidence Layer call on row-expand.
                if p.get("verdict") == "contested":
                    rendered = decide_advisory_render(p, ai_query=ai_query)
                    if rendered is not None:
                        render_ai_advisory_block(rendered)
                        # Persist if maybe_render emitted a payload (LP-AI-CACHE-001).
                        if rendered.get("persist"):
                            _persist_ai_recommendation(
                                engine, p["facility_id"], rendered["persist"],
                            )


def _persist_ai_recommendation(engine, facility_id: str, persist: dict) -> None:
    from phantom_census.lakebase.ai_cache_writes import persist_ai_recommendation
    persist_ai_recommendation(
        engine,
        facility_id=facility_id,
        recommendation=persist["ai_recommendation"],
        evidence_state=persist["ai_recommendation_evidence_state"],
    )
