"""Tests for the geoBoundaries → desert_scores join used by PW-MAP-001."""
from __future__ import annotations

import json

import pandas as pd

from phantom_census.planner_workspace.geometry_loader import (
    load_districts_geojson,
    resolve_geoboundaries_path,
)


def _scores() -> pd.DataFrame:
    return pd.DataFrame([
        {"district_id": "IND-ADM2-MUM", "district_name": "Mumbai",
         "state_name": "Maharashtra",
         "raw_desert_score": 0.30, "adjusted_desert_score": 0.32,
         "phantom_count": 2, "verified_facility_count": 80},
        {"district_id": "IND-ADM2-BEED", "district_name": "Beed",
         "state_name": "Maharashtra",
         "raw_desert_score": 0.60, "adjusted_desert_score": 0.84,
         "phantom_count": 4, "verified_facility_count": 12},
    ])


def _write_fc(tmp_path, features) -> str:
    path = tmp_path / "india_adm2.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    return str(path)


# @spec PW-MAP-001
def test_loader_returns_none_when_no_path_configured(monkeypatch):
    monkeypatch.delenv("GEOBOUNDARIES_ADM2_PATH", raising=False)
    # Default data/geoBoundaries/india_adm2.geojson is not in tree, so the
    # loader correctly returns None.
    assert resolve_geoboundaries_path() is None
    assert load_districts_geojson(_scores()) is None


# @spec PW-MAP-001
def test_loader_joins_scores_into_feature_properties(monkeypatch, tmp_path):
    features = [
        {"type": "Feature",
         "geometry": {"type": "Polygon", "coordinates": [[[72.7, 18.85],
                                                          [73.0, 18.85],
                                                          [73.0, 19.20],
                                                          [72.7, 19.20],
                                                          [72.7, 18.85]]]},
         "properties": {"shapeID": "IND-ADM2-MUM", "shapeName": "Mumbai"}},
        {"type": "Feature",
         "geometry": {"type": "Polygon", "coordinates": [[[75.5, 18.7],
                                                          [76.5, 18.7],
                                                          [76.5, 19.4],
                                                          [75.5, 19.4],
                                                          [75.5, 18.7]]]},
         "properties": {"shapeID": "IND-ADM2-BEED", "shapeName": "Beed"}},
    ]
    monkeypatch.setenv("GEOBOUNDARIES_ADM2_PATH", _write_fc(tmp_path, features))

    fc = load_districts_geojson(_scores())
    assert fc is not None
    assert fc["type"] == "FeatureCollection"
    props_by_id = {f["properties"]["shapeID"]: f["properties"]
                   for f in fc["features"]}
    beed = props_by_id["IND-ADM2-BEED"]
    assert beed["raw_desert_score"] == 0.60
    assert beed["adjusted_desert_score"] == 0.84
    assert beed["phantom_count"] == 4


# @spec PW-MAP-001
def test_loader_handles_features_without_matching_score(monkeypatch, tmp_path):
    features = [
        {"type": "Feature",
         "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1],
                                                          [0, 1], [0, 0]]]},
         "properties": {"shapeID": "IND-ADM2-UNKNOWN"}},
    ]
    monkeypatch.setenv("GEOBOUNDARIES_ADM2_PATH", _write_fc(tmp_path, features))

    fc = load_districts_geojson(_scores())
    assert fc is not None
    feat = fc["features"][0]
    # Features with no matching score get null scores so the GeoJsonLayer's
    # color callback can branch.
    assert feat["properties"]["raw_desert_score"] is None
    assert feat["properties"]["adjusted_desert_score"] is None
