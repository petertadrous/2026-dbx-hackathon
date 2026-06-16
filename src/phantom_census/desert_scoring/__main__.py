"""Desert-scoring batch CLI.

Example::

    LAKEBASE_URL=postgresql+psycopg://... \\
    python -m phantom_census.desert_scoring \\
        --districts data/geoBoundaries-IND-ADM2.geojson \\
        --nfhs data/nfhs5_district.csv \\
        --capability maternity
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from phantom_census.lakebase.engine import get_engine

from .batch import run_desert_scoring


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m phantom_census.desert_scoring",
        description="Compute desert scores + render tile layers; write to Lakebase.",
    )
    p.add_argument("--districts", type=Path, required=True,
                   help="geoBoundaries ADM2 GeoJSON")
    p.add_argument("--nfhs", type=Path, required=True,
                   help="NFHS-5 district indicator CSV")
    p.add_argument("--capability", default="maternity")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    nfhs = pd.read_csv(args.nfhs)
    if "district_id" not in nfhs.columns and "district" in nfhs.columns:
        nfhs = nfhs.rename(columns={"district": "district_id"})
    if "state_name" not in nfhs.columns and "state" in nfhs.columns:
        nfhs = nfhs.rename(columns={"state": "state_name"})
    engine = get_engine()
    n = run_desert_scoring(engine, capability=args.capability,
                           districts_path=args.districts, nfhs=nfhs)
    print(f"desert_scoring: wrote {n} district rows", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
