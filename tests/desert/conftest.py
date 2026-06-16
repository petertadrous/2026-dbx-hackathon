"""Synthetic fixtures for desert-scoring tests."""
from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon


@pytest.fixture
def small_facilities_with_district() -> pd.DataFrame:
    """Three districts in Maharashtra; F1/F2/F3 real, F4 phantom in BEED."""
    return pd.DataFrame([
        {"facility_id": "F1", "district_id": "BEED", "spatial_district": "Beed"},
        {"facility_id": "F2", "district_id": "BEED", "spatial_district": "Beed"},
        {"facility_id": "F3", "district_id": "MUM",  "spatial_district": "Mumbai"},
        {"facility_id": "F4", "district_id": "BEED", "spatial_district": "Beed"},
        {"facility_id": "F5", "district_id": "PUN",  "spatial_district": "Pune"},
    ])


@pytest.fixture
def small_verdicts() -> pd.DataFrame:
    return pd.DataFrame([
        {"facility_id": "F1", "verdict": "real"},
        {"facility_id": "F2", "verdict": "real"},
        {"facility_id": "F3", "verdict": "real"},
        {"facility_id": "F4", "verdict": "phantom"},
        {"facility_id": "F5", "verdict": "real"},
    ])


@pytest.fixture
def small_nfhs() -> pd.DataFrame:
    """Beed has a low (bottom-quartile) institutional_delivery_rate.
    PUN's rate is suppressed (`*`) so DS-SCORE-005 fires."""
    return pd.DataFrame([
        {"district_id": "BEED", "district_name": "Beed", "state_name": "Maharashtra",
         "institutional_delivery_rate": 70.0},
        {"district_id": "MUM",  "district_name": "Mumbai", "state_name": "Maharashtra",
         "institutional_delivery_rate": 95.0},
        {"district_id": "PUN",  "district_name": "Pune", "state_name": "Maharashtra",
         "institutional_delivery_rate": "*"},
    ])


@pytest.fixture
def small_districts() -> gpd.GeoDataFrame:
    """District polygons sized for DS-SCORE-006 per-km² density tests.

    Coordinates use a metric-ish projection so polygon `.area` is interpretable
    as km². EPSG:24378 (Kalianpur 1937 / India zone IIb) is reasonable for
    Maharashtra; we approximate with planar squares in unit-area coordinates
    and convert via a constant area_km2 multiplier downstream.
    """
    beed = Polygon([(75.5, 18.7), (76.5, 18.7), (76.5, 19.4), (75.5, 19.4)])
    mum  = Polygon([(72.7, 18.85), (73.0, 18.85), (73.0, 19.20), (72.7, 19.20)])
    pun  = Polygon([(73.7, 18.4), (74.2, 18.4), (74.2, 18.8), (73.7, 18.8)])
    return gpd.GeoDataFrame(
        [
            {"district_id": "BEED", "district_name": "Beed",
             "state_name": "Maharashtra", "geometry": beed, "area_km2": 7000.0},
            {"district_id": "MUM",  "district_name": "Mumbai",
             "state_name": "Maharashtra", "geometry": mum, "area_km2": 500.0},
            {"district_id": "PUN",  "district_name": "Pune",
             "state_name": "Maharashtra", "geometry": pun, "area_km2": 1500.0},
        ],
        crs="EPSG:4326",
    )
