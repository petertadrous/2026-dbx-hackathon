"""Tests for the Defender.

Covers EE-DEF-001..005. Encodes the E7 resolution: distinct URLs measured
at the registrable-domain (eTLD+1) level.
"""
from __future__ import annotations

import pandas as pd

from phantom_census.existence_engine import defender
from phantom_census.existence_engine.types import TestName, Verdict


# @spec EE-DEF-003
def test_distinct_domains_collapses_subdomains():
    text = "Visit https://www.apollohospitals.com and https://care.apollohospitals.com"
    assert defender.distinct_registrable_domains(text) == 1


# @spec EE-DEF-003
def test_distinct_domains_counts_two_different_registrable_domains():
    text = "Refs https://apollohospitals.com and https://medanta.org/about"
    assert defender.distinct_registrable_domains(text) == 2


# @spec EE-DEF-003
def test_distinct_domains_zero_when_none():
    assert defender.distinct_registrable_domains("Plain text") == 0


# @spec EE-DEF-002
def test_hfr_match_by_name_and_district(hfr_minimal):
    fac = pd.Series({"facility_name": "municipal general hospital", "district": "Mumbai"})
    assert defender.hfr_match(fac, hfr_minimal) is not None


# @spec EE-DEF-002
def test_hfr_no_match_when_district_differs(hfr_minimal):
    fac = pd.Series({"facility_name": "Municipal General Hospital", "district": "Patna"})
    assert defender.hfr_match(fac, hfr_minimal) is None


# @spec EE-DEF-001, EE-DEF-002, EE-DEF-004
def test_defender_upgrades_phantom_to_contested_on_hfr_match(hfr_minimal):
    verdicts = pd.DataFrame(
        [
            {"facility_id": "F1", "verdict": Verdict.PHANTOM.value,
             "reason": None, "test_outcome_vector": []}
        ]
    )
    facilities = pd.DataFrame(
        [
            {"facility_id": "F1",
             "facility_name": "Municipal General Hospital",
             "district": "Mumbai",
             "description": ""}
        ]
    )
    upd, rescue = defender.run_defender(verdicts, facilities, hfr_minimal)
    assert upd.iloc[0]["verdict"] == Verdict.CONTESTED.value
    assert len(rescue) == 1
    assert rescue.iloc[0]["test_name"] == TestName.DEFENDER_RESCUE.value


# @spec EE-DEF-003, EE-DEF-004
def test_defender_upgrades_on_two_distinct_url_domains(hfr_minimal):
    verdicts = pd.DataFrame(
        [
            {"facility_id": "F2", "verdict": Verdict.PHANTOM.value,
             "reason": None, "test_outcome_vector": []}
        ]
    )
    facilities = pd.DataFrame(
        [
            {"facility_id": "F2",
             "facility_name": "Random Clinic",
             "district": "Patna",
             "description": "Refs https://apollohospitals.com and https://medanta.org"}
        ]
    )
    upd, _ = defender.run_defender(verdicts, facilities, hfr_minimal)
    assert upd.iloc[0]["verdict"] == Verdict.CONTESTED.value


# @spec EE-DEF-004
def test_defender_never_upgrades_real():
    """Even with strong rescue signals, a 'real' verdict is not touched."""
    verdicts = pd.DataFrame(
        [
            {"facility_id": "F3", "verdict": Verdict.REAL.value,
             "reason": None, "test_outcome_vector": []}
        ]
    )
    facilities = pd.DataFrame(
        [
            {"facility_id": "F3",
             "facility_name": "Mun Gen Hosp",
             "district": "Mumbai",
             "description": "https://a.com https://b.com"}
        ]
    )
    hfr = pd.DataFrame([{"facility_name": "Mun Gen Hosp", "district": "Mumbai"}])
    upd, rescue = defender.run_defender(verdicts, facilities, hfr)
    assert upd.iloc[0]["verdict"] == Verdict.REAL.value
    assert rescue.empty


# @spec EE-DEF-004
def test_defender_cannot_upgrade_to_real(hfr_minimal):
    """Defender's max upgrade is contested, never real."""
    verdicts = pd.DataFrame(
        [
            {"facility_id": "F4", "verdict": Verdict.PHANTOM.value,
             "reason": None, "test_outcome_vector": []}
        ]
    )
    facilities = pd.DataFrame(
        [
            {"facility_id": "F4",
             "facility_name": "Municipal General Hospital",
             "district": "Mumbai",
             "description": "https://a.com https://b.com"}  # both hfr + URLs
        ]
    )
    upd, _ = defender.run_defender(verdicts, facilities, hfr_minimal)
    assert upd.iloc[0]["verdict"] == Verdict.CONTESTED.value
    assert upd.iloc[0]["verdict"] != Verdict.REAL.value


# @spec EE-DEF-005
def test_defender_rescue_emits_one_test_row_per_upgrade(hfr_minimal):
    verdicts = pd.DataFrame(
        [
            {"facility_id": "F5", "verdict": Verdict.PHANTOM.value,
             "reason": None, "test_outcome_vector": []},
            {"facility_id": "F6", "verdict": Verdict.PHANTOM.value,
             "reason": None, "test_outcome_vector": []},
        ]
    )
    facilities = pd.DataFrame(
        [
            {"facility_id": "F5",
             "facility_name": "Municipal General Hospital",
             "district": "Mumbai", "description": ""},
            {"facility_id": "F6",
             "facility_name": "Unrelated",
             "district": "Patna", "description": "no urls"},
        ]
    )
    _, rescue = defender.run_defender(verdicts, facilities, hfr_minimal)
    assert len(rescue) == 1
    assert rescue.iloc[0]["facility_id"] == "F5"
    assert "evidence_ref" in rescue.columns
