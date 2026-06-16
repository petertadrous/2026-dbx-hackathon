"""Tests for the Bronze data loaders + district_to_state builder."""
from __future__ import annotations

import json

import pandas as pd
import pytest
from shapely.geometry import Polygon

from phantom_census.existence_engine import data_loading


def test_load_facilities_csv(tmp_path):
    src = tmp_path / "facilities.csv"
    src.write_text("facility_id,latitude,longitude,pincode\nF1,19.0,72.8,400001\n")
    df = data_loading.load_facilities(src)
    assert list(df["facility_id"]) == ["F1"]


def test_load_india_post_renames_variants(tmp_path):
    src = tmp_path / "ip.csv"
    src.write_text("Pincode,Districtname,StateName,Latitude,Longitude\n"
                   "400001,Mumbai,Maharashtra,18.95,72.83\n")
    df = data_loading.load_india_post(src)
    assert set(df.columns) >= {"pincode", "district", "state", "latitude", "longitude"}


def test_load_nfhs5_pass_through(tmp_path):
    src = tmp_path / "nfhs.csv"
    src.write_text("district,state,institutional_delivery_rate\nMumbai,Maharashtra,95.0\n")
    df = data_loading.load_nfhs5(src)
    assert df.iloc[0]["state"] == "Maharashtra"


def test_load_districts_renames_shapeName(tmp_path):
    poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    src = tmp_path / "adm2.geojson"
    geo = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"shapeName": "Mumbai"},
                "geometry": poly.__geo_interface__,
            }
        ],
    }
    src.write_text(json.dumps(geo))
    gdf = data_loading.load_districts(src)
    assert "district" in gdf.columns
    assert gdf.iloc[0]["district"] == "Mumbai"
    assert gdf.crs is not None


def test_load_hfr_none_returns_empty():
    df = data_loading.load_hfr(None)
    assert df.empty
    assert set(df.columns) == {"facility_name", "district"}


def test_load_hfr_missing_path_returns_empty(tmp_path):
    df = data_loading.load_hfr(tmp_path / "does-not-exist.csv")
    assert df.empty


def test_build_district_to_state_from_india_post_modal():
    india_post = pd.DataFrame(
        [
            {"district": "Mumbai", "state": "Maharashtra"},
            {"district": "Mumbai", "state": "Maharashtra"},
            {"district": "Mumbai", "state": "Goa"},  # outlier
            {"district": "Patna", "state": "Bihar"},
        ]
    )
    mapping = data_loading.build_district_to_state(india_post)
    assert mapping["Mumbai"] == "Maharashtra"
    assert mapping["Patna"] == "Bihar"


def test_build_district_to_state_augments_from_nfhs():
    india_post = pd.DataFrame(
        [{"district": "Mumbai", "state": "Maharashtra"}]
    )
    nfhs = pd.DataFrame(
        [
            {"district": "Mumbai", "state": "Goa", "institutional_delivery_rate": 95},
            {"district": "Beed", "state": "Maharashtra", "institutional_delivery_rate": 70},
        ]
    )
    mapping = data_loading.build_district_to_state(india_post, nfhs)
    assert mapping["Mumbai"] == "Maharashtra"  # India Post wins
    assert mapping["Beed"] == "Maharashtra"    # NFHS fills the gap
