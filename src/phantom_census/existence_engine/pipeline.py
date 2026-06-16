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

from datasketch import MinHash

from . import nfhs, pin_lookup, spatial, temporal
from .adjudicator import run_adjudicator
from .data_loading import build_district_to_state
from .defender import run_defender
from .minhash import persist_signatures, run_minhash_test


@dataclass
class EngineInputs:
    facilities: pd.DataFrame
    india_post: pd.DataFrame
    nfhs: pd.DataFrame
    districts: gpd.GeoDataFrame
    hfr: pd.DataFrame
    district_to_state: dict[str, str] | None = None
    current_year: int | None = None


@dataclass
class EngineOutputs:
    facility_existence_tests: pd.DataFrame
    phantom_verdicts: pd.DataFrame
    claim_minhash_signatures: dict[str, MinHash]


# @spec EE-PIPE-001..004, EE-HASH-001
def run_engine(inputs: EngineInputs, ran_at: datetime | None = None) -> EngineOutputs:
    ran_at = ran_at or datetime.now(tz=timezone.utc)

    district_to_state = inputs.district_to_state
    if not district_to_state:
        district_to_state = build_district_to_state(inputs.india_post, inputs.nfhs)

    current_year = inputs.current_year or ran_at.year

    pin_centroids = pin_lookup.build_pin_centroids(inputs.india_post)
    facilities_with_district = spatial.assign_districts(inputs.facilities, inputs.districts)

    signatures: dict[str, MinHash] = {}

    t1 = pin_lookup.run_pin_test(inputs.facilities, pin_centroids)
    t2 = run_minhash_test(inputs.facilities, signatures_out=signatures)
    t3 = spatial.run_spatial_test(inputs.facilities, inputs.districts, inputs.india_post)
    t4 = nfhs.run_nfhs_test(facilities_with_district, inputs.nfhs, district_to_state)
    t5 = temporal.run_temporal_test(inputs.facilities, current_year)

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
        claim_minhash_signatures=signatures,
    )


# @spec EE-HASH-001, EE-PIPE-002, EE-PIPE-003
def write_outputs(outputs: EngineOutputs, out_dir: Path) -> None:
    """Write engine outputs to a local Parquet cache.

    Files written:
      facility_existence_tests.parquet  — long-format test results
      phantom_verdicts.parquet          — one row per facility verdict
      claim_minhash.parquet             — BYTEA cache (EE-HASH-001)

    Lakebase load (operational.* + cache.claim_minhash) is the
    lakebase-persistence segment's responsibility.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs.facility_existence_tests.to_parquet(out_dir / "facility_existence_tests.parquet")
    outputs.phantom_verdicts.to_parquet(out_dir / "phantom_verdicts.parquet")
    persist_signatures(outputs.claim_minhash_signatures, out_dir / "claim_minhash.parquet")
