"""GeoBoundaries ADM2 polygon loader for the pydeck GeoJsonLayer.

The geoBoundaries shapefile is large (~30MB raw, ~5MB simplified) so it's
not committed in-tree. The loader resolves the path from:

    1. The `GEOBOUNDARIES_ADM2_PATH` env var (absolute or relative to cwd).
    2. The default `data/geoBoundaries/india_adm2.geojson` if it exists.
    3. None — the caller falls back to a TextLayer placeholder.

Output shape is a GeoJSON `FeatureCollection` with each feature's properties
enriched with `desert_scores` columns joined on `shapeID`. That matches the
shape pydeck's `GeoJsonLayer` expects via the `data=` arg.

The loader is intentionally side-effect-free; Streamlit-side caching is
applied by the caller via `@st.cache_data`.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd


_DEFAULT_PATH = Path("data") / "geoBoundaries" / "india_adm2.geojson"


def resolve_geoboundaries_path() -> Path | None:
    """Return the configured geoBoundaries path or None when unavailable."""
    env = os.environ.get("GEOBOUNDARIES_ADM2_PATH")
    if env:
        p = Path(env)
        return p if p.exists() else None
    if _DEFAULT_PATH.exists():
        return _DEFAULT_PATH
    return None


def load_districts_geojson(scores: pd.DataFrame) -> dict[str, Any] | None:
    """Load the geoBoundaries FeatureCollection and join scores by `shapeID`.

    Returns None when no geometry source is available (the caller renders
    a TextLayer fallback in that case).

    Each feature's `properties` is enriched with the matching `desert_scores`
    row's columns (`raw_desert_score`, `adjusted_desert_score`,
    `phantom_count`, `verified_facility_count`, `district_name`,
    `state_name`). Features without a matching row keep their original
    properties and carry `raw_desert_score = adjusted_desert_score = null`
    so the pydeck color callback can branch.
    """
    path = resolve_geoboundaries_path()
    if path is None or scores.empty:
        return None

    with path.open("r") as f:
        fc = json.load(f)

    score_by_shape: dict[str, dict[str, Any]] = {
        str(row["district_id"]): {
            "raw_desert_score": float(row["raw_desert_score"]),
            "adjusted_desert_score": float(row["adjusted_desert_score"]),
            "phantom_count": int(row["phantom_count"]),
            "verified_facility_count": int(row["verified_facility_count"]),
            "district_name": row.get("district_name"),
            "state_name": row.get("state_name"),
        }
        for _, row in scores.iterrows()
    }

    for feature in fc.get("features", []):
        props = feature.setdefault("properties", {})
        shape_id = props.get("shapeID")
        joined = score_by_shape.get(str(shape_id))
        if joined is not None:
            props.update(joined)
        else:
            props.setdefault("raw_desert_score", None)
            props.setdefault("adjusted_desert_score", None)

    return fc
