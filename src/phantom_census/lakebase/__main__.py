"""Lakebase admin CLI.

Usage::

    python -m phantom_census.lakebase init
    python -m phantom_census.lakebase load --from out/engine
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from datasketch import MinHash
import numpy as np

from .engine import get_engine
from .migrate import init_schema
from .writer import load_engine_outputs


def _deserialize_signature(blob: bytes) -> MinHash:
    hv = np.frombuffer(bytes(blob), dtype=np.uint32)
    return MinHash(num_perm=128, hashvalues=hv)


def _load_outputs_from_disk(parquet_dir: Path):
    from phantom_census.existence_engine.pipeline import EngineOutputs
    tests = pd.read_parquet(parquet_dir / "facility_existence_tests.parquet")
    verdicts = pd.read_parquet(parquet_dir / "phantom_verdicts.parquet")
    sig_path = parquet_dir / "claim_minhash.parquet"
    signatures: dict[str, MinHash] = {}
    if sig_path.exists():
        sig_df = pd.read_parquet(sig_path)
        for _, row in sig_df.iterrows():
            signatures[row["facility_id"]] = _deserialize_signature(row["signature_bytea"])
    return EngineOutputs(
        facility_existence_tests=tests,
        phantom_verdicts=verdicts,
        claim_minhash_signatures=signatures,
    )


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m phantom_census.lakebase")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Create all Phantom Census tables.")

    load = sub.add_parser("load", help="Load engine Parquet outputs into Lakebase.")
    load.add_argument("--from", dest="src", type=Path, required=True,
                      help="Directory containing facility_existence_tests.parquet etc.")
    load.add_argument("--district-map", type=Path, default=None,
                      help="Optional CSV with columns facility_id,district_id for the xref.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    engine = get_engine()

    if args.cmd == "init":
        init_schema(engine)
        print("lakebase: schema initialized", file=sys.stderr)
        return 0

    if args.cmd == "load":
        outputs = _load_outputs_from_disk(args.src)
        mapping: dict[str, str] = {}
        # Auto-load the xref emitted alongside the parquets unless the caller
        # supplied an explicit override.
        xref_path = args.district_map or (args.src / "facility_district_xref.csv")
        if xref_path.exists():
            xref = pd.read_csv(xref_path)
            mapping = dict(zip(xref["facility_id"], xref["district_id"]))
        stats = load_engine_outputs(
            outputs, engine, ran_at=datetime.now(tz=timezone.utc),
            facility_district_map=mapping,
        )
        print(f"lakebase: loaded {stats}", file=sys.stderr)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
