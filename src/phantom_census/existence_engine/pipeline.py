"""Pipeline — orchestrate all five tests + Adjudicator + Defender.

Implements EE-PIPE-001..004.

Output is filesystem (Parquet) by default per E10. Lakebase load is a separate
segment cascade owned by lakebase-persistence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd

from . import nfhs, pin_lookup, spatial, temporal
from .adjudicator import run_adjudicator
from .defender import run_defender
from .minhash import run_minhash_test


@dataclass
class EngineInputs:
    facilities: pd.DataFrame
    india_post: pd.DataFrame
    nfhs: pd.DataFrame
    districts: gpd.GeoDataFrame
    hfr: pd.DataFrame
    district_to_state: dict[str, str]
    current_year: int


@dataclass
class EngineOutputs:
    facility_existence_tests: pd.DataFrame
    phantom_verdicts: pd.DataFrame


# @spec EE-PIPE-001..004
def run_engine(inputs: EngineInputs, ran_at: datetime | None = None) -> EngineOutputs:
    ran_at = ran_at or datetime.now(tz=timezone.utc)

    pin_centroids = pin_lookup.build_pin_centroids(inputs.india_post)
    facilities_with_district = spatial.assign_districts(inputs.facilities, inputs.districts)

    t1 = pin_lookup.run_pin_test(inputs.facilities, pin_centroids)
    t2 = run_minhash_test(inputs.facilities)
    t3 = spatial.run_spatial_test(inputs.facilities, inputs.districts, inputs.india_post)
    t4 = nfhs.run_nfhs_test(facilities_with_district, inputs.nfhs, inputs.district_to_state)
    t5 = temporal.run_temporal_test(inputs.facilities, inputs.current_year)

    facility_tests = pd.concat([t1, t2, t3, t4, t5], ignore_index=True)
    facility_tests["ran_at"] = ran_at

    verdicts = run_adjudicator(facility_tests)
    facilities_with_name = inputs.facilities.copy()
    if "facility_name" not in facilities_with_name.columns:
        facilities_with_name["facility_name"] = None
    if "district" not in facilities_with_name.columns:
        facilities_with_name = facilities_with_name.merge(
            facilities_with_district[["facility_id", "spatial_district"]],
            on="facility_id", how="left",
        ).rename(columns={"spatial_district": "district"})

    verdicts, rescue_rows = run_defender(verdicts, facilities_with_name, inputs.hfr)

    if not rescue_rows.empty:
        rescue_rows = rescue_rows.copy()
        rescue_rows["ran_at"] = ran_at
        facility_tests = pd.concat([facility_tests, rescue_rows], ignore_index=True)

    verdicts["ran_at"] = ran_at

    return EngineOutputs(
        facility_existence_tests=facility_tests,
        phantom_verdicts=verdicts,
    )


def write_outputs(outputs: EngineOutputs, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs.facility_existence_tests.to_parquet(out_dir / "facility_existence_tests.parquet")
    outputs.phantom_verdicts.to_parquet(out_dir / "phantom_verdicts.parquet")
