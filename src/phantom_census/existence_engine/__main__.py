"""Batch CLI entry point for the existence engine.

Run:
    python -m phantom_census.existence_engine \\
        --facilities data/vf.parquet \\
        --india-post data/india_post.csv \\
        --nfhs data/nfhs5_district.csv \\
        --districts data/geoBoundaries-IND-ADM2.geojson \\
        --hfr data/hfr_snapshot.csv \\
        --out out/existence_engine

Outputs (under `--out`):
    facility_existence_tests.parquet
    phantom_verdicts.parquet
    claim_minhash.parquet

@spec EE-PIPE-001
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .data_loading import (
    load_districts,
    load_facilities,
    load_hfr,
    load_india_post,
    load_nfhs5,
)
from .pipeline import EngineInputs, run_engine, write_outputs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m phantom_census.existence_engine",
        description="Run the offline existence-engine batch over the five input sources.",
    )
    p.add_argument("--facilities", type=Path, required=True,
                   help="VF facility dataset (.parquet or .csv)")
    p.add_argument("--india-post", type=Path, required=True,
                   help="India Post PIN Code Directory (.csv)")
    p.add_argument("--nfhs", type=Path, required=True,
                   help="NFHS-5 district indicator table (.csv)")
    p.add_argument("--districts", type=Path, required=True,
                   help="geoBoundaries India ADM2 polygons (.geojson)")
    p.add_argument("--hfr", type=Path, default=None,
                   help="HFR snapshot (.csv); optional — empty if absent")
    p.add_argument("--out", type=Path, required=True,
                   help="Output directory for Parquet results")
    p.add_argument("--current-year", type=int, default=None,
                   help="Override the year used by Test 5 (defaults to today's year)")
    return p.parse_args(argv)


def run_from_paths(args: argparse.Namespace) -> Path:
    inputs = EngineInputs(
        facilities=load_facilities(args.facilities),
        india_post=load_india_post(args.india_post),
        nfhs=load_nfhs5(args.nfhs),
        districts=load_districts(args.districts),
        hfr=load_hfr(args.hfr),
        district_to_state=None,
        current_year=args.current_year,
    )
    ran_at = datetime.now(tz=timezone.utc)
    outputs = run_engine(inputs, ran_at=ran_at)
    write_outputs(outputs, args.out)
    return args.out


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out = run_from_paths(args)
    print(f"existence-engine: wrote outputs to {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
