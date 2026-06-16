"""Map view — pydeck choropleth + facility scatter + side panel.

@spec PW-MAP-001, PW-MAP-002, PW-MAP-003, PW-MAP-004, PW-MAP-005, PW-MAP-006
"""
from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import Engine, text

from phantom_census.desert_scoring.ranking import phantom_counter
from phantom_census.lakebase.readers import get_desert_scores

from ..geometry_loader import load_districts_geojson
from . import side_panel

INDIA_CENTER = (22.0, 78.5)


def render(engine: Engine, workspace) -> None:
    map_col, panel_col = st.columns([0.6, 0.4])

    with map_col:
        # PW-MAP-002 — raw/adjusted toggle. Sets st.session_state['view']; does
        # NOT issue any Lakebase read.
        view = st.radio(
            "View",
            ("raw", "adjusted"),
            index=0 if workspace.view == "raw" else 1,
            horizontal=True,
            format_func=lambda s: "Raw" if s == "raw" else "Adjusted",
            key="map_view_toggle",
        )
        workspace.view = view

        scores = get_desert_scores(engine, capability=workspace.capability)
        facilities = _load_facilities(engine, capability=workspace.capability)

        # PW-MAP-005 — Phantoms removed counter.
        phantom_total = phantom_counter(scores) if not scores.empty else 0
        st.markdown(f"**Phantoms removed: {phantom_total}**")

        # PW-MAP-001 — pydeck GeoJsonLayer with get_fill_color reading the
        # active score column. PW-MAP-003 — facility ScatterplotLayer with
        # verdict-derived colors. PW-MAP-004 — facility marker color is
        # independent of the toggle.
        _render_pydeck(scores, facilities, view=view)

    with panel_col:
        side_panel.render(engine, workspace)


def _render_pydeck(
    scores: pd.DataFrame, facilities: pd.DataFrame, *, view: str,
) -> None:
    """Render the pydeck Deck. Lazy-imports pydeck so tests without the
    optional `app` dependency can still load this module."""
    try:
        import pydeck as pdk
    except ImportError:
        st.warning(
            "pydeck not installed. Install `phantom-census[app]` to enable the "
            "interactive map.",
        )
        return
    if scores.empty:
        st.info("No desert scores loaded for this capability.")
        return

    score_col = f"{view}_desert_score"
    layers = []

    # PW-MAP-001 — choropleth GeoJsonLayer reading from the geoBoundaries
    # ADM2 FeatureCollection joined to desert_scores on `shapeID`. When the
    # geometry source is not configured, fall back to a TextLayer placeholder
    # so the rest of the app still renders.
    geojson = _cached_load_districts_geojson(scores)
    if geojson is not None:
        layers.append(pdk.Layer(
            "GeoJsonLayer",
            data=geojson,
            get_fill_color=(
                f"[255 * (properties.{score_col} || 0), 30, 30, 180]"
            ),
            get_line_color=[80, 80, 80, 200],
            line_width_min_pixels=0.5,
            pickable=True,
            stroked=True,
            filled=True,
        ))
    else:
        layers.append(pdk.Layer(
            "TextLayer",
            data=scores.to_dict(orient="records"),
            get_position="[1.0, 1.0]",  # placeholder coords
            get_text="district_name",
            get_color=_get_score_color_callback(score_col),
            get_size=14,
            pickable=True,
        ))

    # PW-MAP-003 — facility ScatterplotLayer (green/grey/yellow).
    if not facilities.empty:
        facilities = facilities.copy()
        facilities["color"] = facilities["verdict"].apply(_facility_color)
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=facilities.to_dict(orient="records"),
            get_position="[longitude, latitude]",
            get_fill_color="color",
            get_radius=200,
            pickable=True,
        ))

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            latitude=INDIA_CENTER[0], longitude=INDIA_CENTER[1], zoom=5,
        ),
        map_style="light",
    )
    st.pydeck_chart(deck)


@st.cache_data(show_spinner=False)
def _cached_load_districts_geojson(scores: pd.DataFrame) -> dict | None:
    """Cached wrapper around geometry_loader.load_districts_geojson.

    Streamlit caches the joined FeatureCollection keyed by the scores frame's
    content hash, so repeat tab switches don't re-read the geoBoundaries file.
    Returns None when no geometry source is configured.
    """
    return load_districts_geojson(scores)


def _get_score_color_callback(score_col: str):
    """Return a pydeck `get_color` expression mapping `[0..1]` to a red ramp.

    Pydeck callbacks must be JSON-serializable; here we encode a simple
    R-only ramp: `[int(255 * score), 30, 30, 220]`. The shared scale across
    raw and adjusted views (PW-MAP-001 / DS-MAP-002) is preserved because the
    same expression reads either column at render time.
    """
    return f"[255 * row.{score_col}, 30, 30, 220]"


def _facility_color(verdict: str) -> list[int]:
    """PW-MAP-003 verdict palette."""
    if verdict == "real":
        return [30, 200, 30, 200]  # green
    if verdict == "phantom":
        return [128, 128, 128, 140]  # grey ghost
    if verdict == "contested":
        return [255, 200, 30, 220]  # yellow
    if verdict in ("force-real-planner", "force-phantom-planner"):
        return [120, 120, 220, 220]  # blue
    return [200, 200, 200, 160]


def _load_facilities(engine: Engine, capability: str) -> pd.DataFrame:
    """Read facility scatter data: lat/lon + verdict per facility."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT pv.facility_id, pv.verdict,
                   pv.override_id,
                   x.district_id
            FROM operational.phantom_verdicts pv
            JOIN operational.facility_district_xref x USING (facility_id)
            JOIN operational.facility_capabilities fc USING (facility_id)
            WHERE fc.capability = :capability
        """), {"capability": capability}).mappings().all()
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # vf_facilities lat/lon would normally join here; for the demo we leave
    # the columns null and the ScatterplotLayer no-ops when they're missing.
    df["latitude"] = pd.NA
    df["longitude"] = pd.NA
    return df.dropna(subset=["latitude", "longitude"], how="all")
