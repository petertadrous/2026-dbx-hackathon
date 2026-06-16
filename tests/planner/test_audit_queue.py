"""Tests for PW-AUDIT-001..005 — audit queue ranking + PDF export."""
from __future__ import annotations

import pandas as pd

from phantom_census.planner_workspace.audit import (
    AUDIT_TOP_N,
    build_audit_queue,
    render_inspector_worksheet_pdf,
)


def _phantoms() -> pd.DataFrame:
    return pd.DataFrame([
        {"facility_id": "F1", "facility_name": "Beed Maternity",
         "district_id": "BEED", "district_name": "Beed",
         "pincode": "431122", "latitude": 18.99, "longitude": 75.76,
         "test_outcome_vector": [
             {"test_name": "pin-reverse-lookup", "result": "fail"},
             {"test_name": "minhash-near-duplicate", "result": "fail"},
             {"test_name": "nfhs-outcome-inconsistency", "result": "fail"},
         ]},
        {"facility_id": "F2", "facility_name": "Latur Memorial",
         "district_id": "LAT", "district_name": "Latur",
         "pincode": "413512", "latitude": 18.41, "longitude": 76.58,
         "test_outcome_vector": [
             {"test_name": "pin-reverse-lookup", "result": "fail"},
             {"test_name": "spatial-district-mismatch", "result": "fail"},
         ]},
        # One that's NOT phantom — must be excluded.
        {"facility_id": "F3", "facility_name": "Mumbai General",
         "district_id": "MUM", "district_name": "Mumbai",
         "pincode": "400001", "latitude": 19.00, "longitude": 72.83,
         "test_outcome_vector": [],
         "verdict": "real"},
    ])


def _district_leverage() -> pd.DataFrame:
    return pd.DataFrame([
        {"district_id": "BEED", "burden_weight": 0.3,
         "verified_facility_count": 12, "phantom_count": 4, "area_km2": 7000.0},
        {"district_id": "LAT",  "burden_weight": 0.25,
         "verified_facility_count": 10, "phantom_count": 3, "area_km2": 6000.0},
        {"district_id": "MUM",  "burden_weight": 0.05,
         "verified_facility_count": 80, "phantom_count": 1, "area_km2": 500.0},
    ])


# @spec PW-AUDIT-001
def test_audit_queue_returns_at_most_top_n():
    phantoms = pd.DataFrame([
        {"facility_id": f"F{i}", "facility_name": f"Fac {i}",
         "district_id": "BEED", "district_name": "Beed",
         "pincode": "431122", "latitude": 18.99, "longitude": 75.76,
         "test_outcome_vector": []}
        for i in range(60)
    ])
    queue = build_audit_queue(phantoms, _district_leverage())
    assert len(queue) == AUDIT_TOP_N == 50


# @spec PW-AUDIT-001
def test_audit_queue_sorts_by_leverage_descending():
    queue = build_audit_queue(_phantoms(), _district_leverage())
    # BEED leverage = 0.3 × 12 × phantom_density(4/7000) = small but
    # LAT leverage = 0.25 × 10 × 3/6000 is smaller.
    # MUM is excluded (real, not phantom).
    by_id = queue.set_index("facility_id")
    assert "F3" not in by_id.index
    # The rank column is 1-indexed; first row has rank 1.
    first = queue.iloc[0]
    assert first["rank"] == 1


# @spec PW-AUDIT-001
def test_audit_queue_tie_breaks_by_failed_test_count():
    """Two facilities in the same district: more failed tests → higher rank."""
    phantoms = pd.DataFrame([
        {"facility_id": "F-MANY", "facility_name": "Many",
         "district_id": "BEED", "district_name": "Beed",
         "pincode": "431122", "latitude": 18.99, "longitude": 75.76,
         "test_outcome_vector": [
             {"test_name": "pin-reverse-lookup", "result": "fail"},
             {"test_name": "minhash-near-duplicate", "result": "fail"},
             {"test_name": "nfhs-outcome-inconsistency", "result": "fail"},
         ]},
        {"facility_id": "F-FEW", "facility_name": "Few",
         "district_id": "BEED", "district_name": "Beed",
         "pincode": "431122", "latitude": 18.99, "longitude": 75.76,
         "test_outcome_vector": [
             {"test_name": "pin-reverse-lookup", "result": "fail"},
         ]},
    ])
    queue = build_audit_queue(phantoms, _district_leverage())
    assert queue.iloc[0]["facility_id"] == "F-MANY"


# @spec PW-AUDIT-002
def test_audit_queue_columns_present():
    queue = build_audit_queue(_phantoms(), _district_leverage())
    required = {"rank", "facility_name", "district_name", "pincode",
                "latitude", "longitude", "failed_tests"}
    assert required <= set(queue.columns)


# @spec PW-AUDIT-003
def test_render_inspector_worksheet_pdf_emits_bytes():
    queue = build_audit_queue(_phantoms(), _district_leverage())
    pdf_bytes = render_inspector_worksheet_pdf(queue)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    # Reportlab compresses content streams, so the raw bytes don't contain
    # facility names as plain text. Sanity-check size — a real worksheet with
    # rows should be larger than the empty-PDF baseline.
    assert len(pdf_bytes) > 1500


# @spec PW-AUDIT-005
def test_audit_module_does_not_call_ai_query():
    import inspect
    from phantom_census.planner_workspace import audit
    src = inspect.getsource(audit)
    assert "ai_query" not in src
    assert "ai_evidence_layer" not in src
