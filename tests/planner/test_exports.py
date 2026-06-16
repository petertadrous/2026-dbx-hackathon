"""Tests for PW-EXP-001..005 — scenario CSV + HMIS webhook."""
from __future__ import annotations

import json

import pandas as pd

from phantom_census.planner_workspace.exports import (
    build_hmis_payload,
    serialize_scenario_csv,
)


def _scores() -> pd.DataFrame:
    return pd.DataFrame([
        {"district_id": "BEED", "district_name": "Beed", "state_name": "Maharashtra",
         "raw_desert_score": 0.6, "adjusted_desert_score": 0.84,
         "verified_facility_count": 12, "phantom_count": 4},
        {"district_id": "LAT", "district_name": "Latur", "state_name": "Maharashtra",
         "raw_desert_score": 0.55, "adjusted_desert_score": 0.78,
         "verified_facility_count": 10, "phantom_count": 3},
        {"district_id": "MUM", "district_name": "Mumbai", "state_name": "Maharashtra",
         "raw_desert_score": 0.30, "adjusted_desert_score": 0.32,
         "verified_facility_count": 80, "phantom_count": 2},
    ])


# @spec PW-EXP-001
def test_scenario_csv_has_required_columns():
    csv = serialize_scenario_csv(_scores(), override_notes=[])
    header = csv.splitlines()[0]
    for col in ("district_name", "state", "raw_desert_score",
                "adjusted_desert_score", "phantom_count",
                "verified_facility_count"):
        assert col in header


# @spec PW-EXP-002
def test_hmis_payload_contains_top5_priority_districts():
    payload = build_hmis_payload(_scores())
    data = json.loads(payload)
    assert "priority_districts" in data
    assert len(data["priority_districts"]) <= 5
    # Ordered by adjusted_desert_score descending.
    scores = [d["adjusted_desert_score"] for d in data["priority_districts"]]
    assert scores == sorted(scores, reverse=True)
    assert data["priority_districts"][0]["district_id"] == "BEED"


# @spec PW-EXP-001
def test_scenario_csv_includes_override_notes_in_justification():
    overrides = [
        {"facility_id": "F1", "district_id": "BEED",
         "override_type": "force-phantom", "reason_note": "site visit confirms"},
    ]
    csv = serialize_scenario_csv(_scores(), override_notes=overrides)
    # The override note text or facility_id should appear in the BEED row.
    beed_lines = [ln for ln in csv.splitlines() if "Beed" in ln]
    assert any("site visit confirms" in ln or "F1" in ln for ln in beed_lines)
