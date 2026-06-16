"""Shared synthetic fixtures for existence-engine tests.

Real VF / India Post / NFHS-5 / ADM2 data is not loaded in unit tests.
Each fixture provides the minimum shape the unit under test needs.
"""
from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon


@pytest.fixture
def facilities_minimal() -> pd.DataFrame:
    """Small facilities frame with all columns the engine reads."""
    return pd.DataFrame(
        [
            {
                "facility_id": "F001",
                "latitude": 19.0760,
                "longitude": 72.8777,
                "pincode": "400001",
                "yearEstablished": 1995,
                "capability": ["Maternity", "NICU"],
                "procedure": ["C-section"],
                "equipment": ["Ventilator", "Ultrasound"],
                "description": "Verified municipal hospital in Mumbai.",
                "address_stateOrRegion": "Maharashtra",
            }
        ]
    )


@pytest.fixture
def india_post_minimal() -> pd.DataFrame:
    """Two PINs, one with fan-out across 3 post offices in same district."""
    return pd.DataFrame(
        [
            {"pincode": "400001", "district": "Mumbai", "state": "Maharashtra",
             "latitude": 18.95, "longitude": 72.83},
            {"pincode": "400001", "district": "Mumbai", "state": "Maharashtra",
             "latitude": 18.96, "longitude": 72.84},
            {"pincode": "400001", "district": "Mumbai", "state": "Maharashtra",
             "latitude": 18.94, "longitude": 72.82},
            {"pincode": "800001", "district": "Patna", "state": "Bihar",
             "latitude": 25.61, "longitude": 85.13},
        ]
    )


@pytest.fixture
def districts_minimal() -> gpd.GeoDataFrame:
    """Two non-overlapping district polygons covering the test facility coordinates."""
    mumbai = Polygon([(72.7, 18.85), (73.0, 18.85), (73.0, 19.20), (72.7, 19.20)])
    patna = Polygon([(85.0, 25.5), (85.3, 25.5), (85.3, 25.7), (85.0, 25.7)])
    return gpd.GeoDataFrame(
        [
            {"district": "Mumbai", "state": "Maharashtra", "geometry": mumbai},
            {"district": "Patna", "state": "Bihar", "geometry": patna},
        ],
        crs="EPSG:4326",
    )


@pytest.fixture
def nfhs_minimal() -> pd.DataFrame:
    """Two districts each in two states, one in bottom quartile per state."""
    return pd.DataFrame(
        [
            {"district": "Mumbai", "state": "Maharashtra", "institutional_delivery_rate": 95.0},
            {"district": "Pune", "state": "Maharashtra", "institutional_delivery_rate": 92.0},
            {"district": "Nashik", "state": "Maharashtra", "institutional_delivery_rate": 88.0},
            {"district": "Beed", "state": "Maharashtra", "institutional_delivery_rate": 70.0},
            {"district": "Patna", "state": "Bihar", "institutional_delivery_rate": 80.0},
            {"district": "Gaya", "state": "Bihar", "institutional_delivery_rate": 60.0},
            {"district": "Sheohar", "state": "Bihar", "institutional_delivery_rate": 50.0},
            {"district": "Araria", "state": "Bihar", "institutional_delivery_rate": 25.0},
        ]
    )


@pytest.fixture
def district_to_state() -> dict[str, str]:
    return {
        "Mumbai": "Maharashtra",
        "Pune": "Maharashtra",
        "Nashik": "Maharashtra",
        "Beed": "Maharashtra",
        "Patna": "Bihar",
        "Gaya": "Bihar",
        "Sheohar": "Bihar",
        "Araria": "Bihar",
    }


@pytest.fixture
def hfr_minimal() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"facility_name": "Municipal General Hospital", "district": "Mumbai"},
        ]
    )
