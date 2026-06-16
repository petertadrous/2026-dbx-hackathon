"""Smoke test for the existence-engine CLI.

Builds tiny on-disk fixtures, runs the CLI end-to-end, asserts output files.
"""
from __future__ import annotations

import json

import pandas as pd
from shapely.geometry import Polygon

from phantom_census.existence_engine.__main__ import main


def _write_fixtures(tmp_path):
    facilities = pd.DataFrame(
        [
            {"facility_id": "F1", "latitude": 19.0, "longitude": 72.88,
             "pincode": "400001", "yearEstablished": 1995,
             "capability": ["Cardiology"], "procedure": ["CABG"],
             "equipment": ["ECG"], "description": ""},
        ]
    )
    fpath = tmp_path / "vf.parquet"
    facilities.to_parquet(fpath)

    india_post = pd.DataFrame(
        [
            {"pincode": "400001", "district": "Mumbai", "state": "Maharashtra",
             "latitude": 18.95, "longitude": 72.83},
        ]
    )
    ipath = tmp_path / "ip.csv"
    india_post.to_csv(ipath, index=False)

    nfhs = pd.DataFrame(
        [
            {"district": "Mumbai", "state": "Maharashtra",
             "institutional_delivery_rate": 95.0},
            {"district": "Pune", "state": "Maharashtra",
             "institutional_delivery_rate": 92.0},
            {"district": "Nashik", "state": "Maharashtra",
             "institutional_delivery_rate": 88.0},
            {"district": "Beed", "state": "Maharashtra",
             "institutional_delivery_rate": 70.0},
        ]
    )
    npath = tmp_path / "nfhs.csv"
    nfhs.to_csv(npath, index=False)

    mumbai = Polygon([(72.7, 18.85), (73.0, 18.85), (73.0, 19.20), (72.7, 19.20)])
    geo = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"shapeName": "Mumbai"},
                "geometry": mumbai.__geo_interface__,
            }
        ],
    }
    dpath = tmp_path / "adm2.geojson"
    dpath.write_text(json.dumps(geo))

    return fpath, ipath, npath, dpath


# @spec EE-PIPE-001, EE-PIPE-002, EE-PIPE-003
def test_cli_writes_three_output_files(tmp_path):
    fpath, ipath, npath, dpath = _write_fixtures(tmp_path)
    out_dir = tmp_path / "out"

    code = main([
        "--facilities", str(fpath),
        "--india-post", str(ipath),
        "--nfhs", str(npath),
        "--districts", str(dpath),
        "--out", str(out_dir),
        "--current-year", "2026",
    ])
    assert code == 0
    assert (out_dir / "facility_existence_tests.parquet").exists()
    assert (out_dir / "phantom_verdicts.parquet").exists()
    assert (out_dir / "claim_minhash.parquet").exists()

    verdicts = pd.read_parquet(out_dir / "phantom_verdicts.parquet")
    assert len(verdicts) == 1
    assert verdicts.iloc[0]["facility_id"] == "F1"
    assert verdicts.iloc[0]["verdict"] in {"phantom", "real", "contested"}


# @spec EE-PIPE-001
def test_cli_handles_missing_hfr_gracefully(tmp_path):
    fpath, ipath, npath, dpath = _write_fixtures(tmp_path)
    out_dir = tmp_path / "out"

    code = main([
        "--facilities", str(fpath),
        "--india-post", str(ipath),
        "--nfhs", str(npath),
        "--districts", str(dpath),
        "--out", str(out_dir),
    ])
    assert code == 0
