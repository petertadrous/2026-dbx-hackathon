"""Test 1 — PIN reverse-lookup (veto-capable).

Implements EE-PIN-001..006.
"""
from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

from .types import TestName, TestResult

DISTANCE_FAIL_KM = 50.0
EARTH_RADIUS_KM = 6371.0088
_PIN_RE = re.compile(r"^\d{6}$")
_REQUIRED_INDIA_POST_COLS = {"pincode", "district", "latitude", "longitude"}


# @spec EE-PIN-001
def parse_pincode(raw: object) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return None
    return s if _PIN_RE.match(s) else None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


# @spec EE-PIN-002
def build_pin_centroids(india_post_df: pd.DataFrame) -> pd.DataFrame:
    if not _REQUIRED_INDIA_POST_COLS.issubset(india_post_df.columns):
        return pd.DataFrame(columns=["pincode", "latitude", "longitude"])

    df = india_post_df.dropna(subset=["pincode", "latitude", "longitude"])
    if df.empty:
        return pd.DataFrame(columns=["pincode", "latitude", "longitude"])

    df = df.copy()
    df["pincode"] = df["pincode"].astype(str).str.strip()
    df = df[df["pincode"].apply(lambda p: isinstance(p, str) and bool(_PIN_RE.match(p)))]
    if df.empty:
        return pd.DataFrame(columns=["pincode", "latitude", "longitude"])

    deduped = df.drop_duplicates(subset=["pincode", "district", "latitude", "longitude"])
    centroids = (
        deduped.groupby("pincode", as_index=False)
        .agg(latitude=("latitude", "mean"), longitude=("longitude", "mean"))
    )
    return centroids


# @spec EE-PIN-001, EE-PIN-002, EE-PIN-003, EE-PIN-004, EE-PIN-005, EE-PIN-006
def run_pin_test(facilities: pd.DataFrame, pin_centroids: pd.DataFrame) -> pd.DataFrame:
    centroid_map: dict[str, tuple[float, float]] = {
        row["pincode"]: (row["latitude"], row["longitude"])
        for _, row in pin_centroids.iterrows()
    }

    rows: list[dict] = []
    for _, fac in facilities.iterrows():
        fac_id = fac["facility_id"]
        pin = parse_pincode(fac.get("pincode"))
        lat, lon = fac.get("latitude"), fac.get("longitude")
        has_latlon = lat is not None and lon is not None and not (
            isinstance(lat, float) and math.isnan(lat)
        ) and not (isinstance(lon, float) and math.isnan(lon))

        if pin is None or not has_latlon or pin not in centroid_map:
            rows.append(_row(fac_id, TestResult.INDETERMINATE, None))
            continue

        pin_lat, pin_lon = centroid_map[pin]
        d = haversine_km(float(lat), float(lon), float(pin_lat), float(pin_lon))
        if d > DISTANCE_FAIL_KM:
            rows.append(_row(fac_id, TestResult.FAIL, {
                "distance_km": d, "pin_lat": float(pin_lat), "pin_lon": float(pin_lon),
            }))
        else:
            rows.append(_row(fac_id, TestResult.PASS, {"distance_km": d}))

    return pd.DataFrame(rows)


def _row(fac_id: str, result: TestResult, evidence_ref: dict | None) -> dict:
    return {
        "facility_id": fac_id,
        "test_name": TestName.PIN_LOOKUP.value,
        "result": result.value,
        "evidence_ref": evidence_ref,
    }
