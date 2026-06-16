"""Scenario CSV + mock HMIS webhook payload builders.

@spec PW-EXP-001, PW-EXP-002, PW-EXP-003, PW-EXP-004, PW-EXP-005
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any

import pandas as pd

HMIS_TOP_PRIORITY_COUNT = 5


# @spec PW-EXP-001
def serialize_scenario_csv(
    scores: pd.DataFrame,
    override_notes: list[dict[str, Any]],
) -> str:
    """CKAN-compatible CSV — district + state + scores + counts + per-district overrides."""
    overrides_by_district: dict[str, list[str]] = {}
    for ovr in override_notes or []:
        district_id = ovr.get("district_id")
        if not district_id:
            continue
        note = (
            f"{ovr.get('facility_id', '')}: {ovr.get('override_type', '')} "
            f"({ovr.get('reason_note', '')})"
        ).strip()
        overrides_by_district.setdefault(district_id, []).append(note)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "district_id", "district_name", "state",
        "raw_desert_score", "adjusted_desert_score",
        "phantom_count", "verified_facility_count",
        "override_notes",
    ])
    for _, r in scores.iterrows():
        notes = "; ".join(overrides_by_district.get(r["district_id"], []))
        writer.writerow([
            r["district_id"], r["district_name"], r["state_name"],
            f"{r['raw_desert_score']:.4f}", f"{r['adjusted_desert_score']:.4f}",
            int(r["phantom_count"]), int(r["verified_facility_count"]),
            notes,
        ])
    return buf.getvalue()


# @spec PW-EXP-002
def build_hmis_payload(scores: pd.DataFrame) -> str:
    """JSON payload POSTed to the mock HMIS webhook.

    Contains the top-5 priority districts by `adjusted_desert_score` descending.
    """
    top = scores.sort_values("adjusted_desert_score", ascending=False).head(
        HMIS_TOP_PRIORITY_COUNT
    )
    payload = {
        "priority_districts": [
            {
                "district_id": r["district_id"],
                "district_name": r["district_name"],
                "state_name": r["state_name"],
                "adjusted_desert_score": float(r["adjusted_desert_score"]),
                "phantom_count": int(r["phantom_count"]),
            }
            for _, r in top.iterrows()
        ],
    }
    return json.dumps(payload, separators=(",", ":"))
