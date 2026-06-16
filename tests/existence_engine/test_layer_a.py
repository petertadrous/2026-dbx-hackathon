"""Tests for Defender Layer A — structured-field corroboration (post-Adjudicator).

Covers EE-LAYER-A-001..008. Layer A patches phantom→contested when any of
three signals fires (url-mentions, hfr-match, nfhs-named-staff) and records
the rescue trace in `phantom_verdicts.rescue_applied` JSONB only — never
writes to `facility_existence_tests`.
"""
from __future__ import annotations

import pandas as pd

from phantom_census.existence_engine import layer_a
from phantom_census.existence_engine.types import Verdict


def _verdicts(rows: list[dict]) -> pd.DataFrame:
    """Build a phantom_verdicts frame with dual-verdict columns."""
    base = []
    for r in rows:
        base.append({
            "facility_id": r["facility_id"],
            "adjudicator_verdict": r["adjudicator_verdict"],
            "verdict": r["adjudicator_verdict"],
            "rescue_applied": None,
            "test_outcome_vector": r.get("test_outcome_vector", []),
        })
    return pd.DataFrame(base)


# @spec EE-LAYER-A-002
def test_url_mentions_signal_fires_with_two_distinct_non_self_published_domains():
    verdicts = _verdicts([{"facility_id": "F1", "adjudicator_verdict": Verdict.PHANTOM.value}])
    facilities = pd.DataFrame([{
        "facility_id": "F1",
        "facility_name": "Mumbai Care",
        "description": "Featured on https://news.example.com/article and https://health.in/listing.",
        "district": "Mumbai",
    }])
    hfr = pd.DataFrame(columns=["facility_name", "district"])
    nfhs_staff = pd.DataFrame(columns=["district", "staff_name"])
    out = layer_a.run_layer_a(verdicts, facilities, hfr, nfhs_staff)
    row = out.iloc[0]
    assert row["verdict"] == Verdict.CONTESTED.value
    assert row["adjudicator_verdict"] == Verdict.PHANTOM.value
    assert "url-mentions" in {s["signal"] for s in row["rescue_applied"]["signals"]}


# @spec EE-LAYER-A-002
def test_url_mentions_signal_does_not_fire_on_single_url():
    verdicts = _verdicts([{"facility_id": "F1", "adjudicator_verdict": Verdict.PHANTOM.value}])
    facilities = pd.DataFrame([{
        "facility_id": "F1",
        "facility_name": "Solo Clinic",
        "description": "Visit https://only-one.com",
        "district": "Mumbai",
    }])
    out = layer_a.run_layer_a(
        verdicts, facilities,
        pd.DataFrame(columns=["facility_name", "district"]),
        pd.DataFrame(columns=["district", "staff_name"]),
    )
    assert out.iloc[0]["verdict"] == Verdict.PHANTOM.value
    assert out.iloc[0]["rescue_applied"] is None


# @spec EE-LAYER-A-002
def test_url_mentions_excludes_self_published_domain():
    """A URL whose domain tokens overlap with the facility name is 'self-published'."""
    verdicts = _verdicts([{"facility_id": "F1", "adjudicator_verdict": Verdict.PHANTOM.value}])
    facilities = pd.DataFrame([{
        "facility_id": "F1",
        "facility_name": "Apollo Hospital",
        "description": "https://apollohospital.com and https://apolloservices.in",
        "district": "Mumbai",
    }])
    out = layer_a.run_layer_a(
        verdicts, facilities,
        pd.DataFrame(columns=["facility_name", "district"]),
        pd.DataFrame(columns=["district", "staff_name"]),
    )
    assert out.iloc[0]["verdict"] == Verdict.PHANTOM.value


# @spec EE-LAYER-A-003
def test_hfr_match_signal_fires_on_exact_name_district_match():
    verdicts = _verdicts([{"facility_id": "F1", "adjudicator_verdict": Verdict.PHANTOM.value}])
    facilities = pd.DataFrame([{
        "facility_id": "F1",
        "facility_name": "Municipal General Hospital",
        "description": "",
        "district": "Mumbai",
    }])
    hfr = pd.DataFrame([{
        "facility_name": "Municipal General Hospital", "district": "Mumbai",
    }])
    out = layer_a.run_layer_a(
        verdicts, facilities, hfr,
        pd.DataFrame(columns=["district", "staff_name"]),
    )
    row = out.iloc[0]
    assert row["verdict"] == Verdict.CONTESTED.value
    assert "hfr-match" in {s["signal"] for s in row["rescue_applied"]["signals"]}


# @spec EE-LAYER-A-003
def test_hfr_match_tolerates_levenshtein_two_on_name():
    verdicts = _verdicts([{"facility_id": "F1", "adjudicator_verdict": Verdict.PHANTOM.value}])
    facilities = pd.DataFrame([{
        "facility_id": "F1",
        "facility_name": "Municpal General Hospital",  # 1-edit typo
        "description": "",
        "district": "Mumbai",
    }])
    hfr = pd.DataFrame([{
        "facility_name": "Municipal General Hospital", "district": "Mumbai",
    }])
    out = layer_a.run_layer_a(
        verdicts, facilities, hfr,
        pd.DataFrame(columns=["district", "staff_name"]),
    )
    assert out.iloc[0]["verdict"] == Verdict.CONTESTED.value


# @spec EE-LAYER-A-004
def test_nfhs_named_staff_signal_fires_when_description_lists_district_staff():
    verdicts = _verdicts([{"facility_id": "F1", "adjudicator_verdict": Verdict.PHANTOM.value}])
    facilities = pd.DataFrame([{
        "facility_id": "F1",
        "facility_name": "Some Clinic",
        "description": "Lead doctor Dr. Anjali Sharma and Dr. Priya Patel attending.",
        "district": "Mumbai",
    }])
    nfhs_staff = pd.DataFrame([
        {"district": "Mumbai", "staff_name": "Anjali Sharma"},
        {"district": "Mumbai", "staff_name": "Vikram Singh"},
    ])
    out = layer_a.run_layer_a(
        verdicts, facilities,
        pd.DataFrame(columns=["facility_name", "district"]),
        nfhs_staff,
    )
    row = out.iloc[0]
    assert row["verdict"] == Verdict.CONTESTED.value
    assert "nfhs-named-staff" in {s["signal"] for s in row["rescue_applied"]["signals"]}


# @spec EE-LAYER-A-005
def test_rescue_applied_payload_records_signals_and_evidence_refs():
    verdicts = _verdicts([{"facility_id": "F1", "adjudicator_verdict": Verdict.PHANTOM.value}])
    facilities = pd.DataFrame([{
        "facility_id": "F1",
        "facility_name": "Municipal General Hospital",
        "description": "https://news.example.com/a https://health.in/b",
        "district": "Mumbai",
    }])
    hfr = pd.DataFrame([{
        "facility_name": "Municipal General Hospital", "district": "Mumbai",
    }])
    out = layer_a.run_layer_a(
        verdicts, facilities, hfr,
        pd.DataFrame(columns=["district", "staff_name"]),
    )
    payload = out.iloc[0]["rescue_applied"]
    assert isinstance(payload, dict)
    assert "signals" in payload
    assert "evidence_refs" in payload
    signal_names = {s["signal"] for s in payload["signals"]}
    assert {"hfr-match", "url-mentions"} <= signal_names


# @spec EE-LAYER-A-005
def test_adjudicator_verdict_preserved_when_layer_a_patches():
    verdicts = _verdicts([{"facility_id": "F1", "adjudicator_verdict": Verdict.PHANTOM.value}])
    facilities = pd.DataFrame([{
        "facility_id": "F1",
        "facility_name": "Municipal General Hospital",
        "description": "",
        "district": "Mumbai",
    }])
    hfr = pd.DataFrame([{
        "facility_name": "Municipal General Hospital", "district": "Mumbai",
    }])
    out = layer_a.run_layer_a(
        verdicts, facilities, hfr,
        pd.DataFrame(columns=["district", "staff_name"]),
    )
    assert out.iloc[0]["adjudicator_verdict"] == Verdict.PHANTOM.value


# @spec EE-LAYER-A-006
def test_layer_a_never_upgrades_to_real():
    """Max upgrade is phantom→contested; layer A doesn't touch real verdicts either."""
    verdicts = _verdicts([{"facility_id": "F1", "adjudicator_verdict": Verdict.REAL.value}])
    facilities = pd.DataFrame([{
        "facility_id": "F1",
        "facility_name": "Solid Hospital",
        "description": "https://news.com/a https://other.com/b",
        "district": "Mumbai",
    }])
    out = layer_a.run_layer_a(
        verdicts, facilities,
        pd.DataFrame(columns=["facility_name", "district"]),
        pd.DataFrame(columns=["district", "staff_name"]),
    )
    assert out.iloc[0]["verdict"] == Verdict.REAL.value
    assert out.iloc[0]["rescue_applied"] is None


# @spec EE-LAYER-A-007
def test_no_signal_means_verdict_and_rescue_unchanged():
    verdicts = _verdicts([{"facility_id": "F1", "adjudicator_verdict": Verdict.PHANTOM.value}])
    facilities = pd.DataFrame([{
        "facility_id": "F1",
        "facility_name": "Lonely Clinic",
        "description": "Plain description with no URLs.",
        "district": "Mumbai",
    }])
    out = layer_a.run_layer_a(
        verdicts, facilities,
        pd.DataFrame(columns=["facility_name", "district"]),
        pd.DataFrame(columns=["district", "staff_name"]),
    )
    assert out.iloc[0]["verdict"] == Verdict.PHANTOM.value
    assert out.iloc[0]["rescue_applied"] is None


# @spec EE-LAYER-A-008
def test_layer_a_does_not_write_facility_existence_tests_rows():
    """Layer A signature returns only the patched verdicts table — no test rows."""
    verdicts = _verdicts([{"facility_id": "F1", "adjudicator_verdict": Verdict.PHANTOM.value}])
    facilities = pd.DataFrame([{
        "facility_id": "F1",
        "facility_name": "Municipal General Hospital",
        "description": "",
        "district": "Mumbai",
    }])
    hfr = pd.DataFrame([{
        "facility_name": "Municipal General Hospital", "district": "Mumbai",
    }])
    out = layer_a.run_layer_a(
        verdicts, facilities, hfr,
        pd.DataFrame(columns=["district", "staff_name"]),
    )
    assert isinstance(out, pd.DataFrame)
    # Layer A returns ONLY verdicts (single DataFrame) — no rescue-test-row second return.
    # If implementation accidentally returned a tuple, this catches it.
