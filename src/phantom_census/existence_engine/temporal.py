"""Test 5 — Temporal implausibility (supporting).

Implements EE-TEMP-001..005.
"""
from __future__ import annotations

import re

import pandas as pd

from .types import TestName, TestResult

HIGH_ACUITY_TERMS = ("icu", "trauma", "nicu", "transplant")
_HIGH_ACUITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in HIGH_ACUITY_TERMS) + r")\b",
    re.IGNORECASE,
)

MIN_PLAUSIBLE_YEAR = 1600


def _join(field: object) -> str:
    if field is None:
        return ""
    if isinstance(field, (list, tuple)):
        return " ".join(str(x) for x in field if x is not None)
    return str(field)


# @spec EE-TEMP-001
def parse_year(raw: object) -> int | None:
    if raw is None:
        return None
    try:
        if isinstance(raw, float) and pd.isna(raw):
            return None
    except (TypeError, ValueError):
        pass
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return None
    if not re.fullmatch(r"\d{4}", s):
        return None
    return int(s)


# @spec EE-TEMP-004
def claims_high_acuity(capability: object, description: object) -> str | None:
    text = (_join(capability) + " " + _join(description)).lower()
    m = _HIGH_ACUITY_RE.search(text)
    return m.group(1).lower() if m else None


# @spec EE-TEMP-001..005
def run_temporal_test(facilities: pd.DataFrame, current_year: int) -> pd.DataFrame:
    high_acuity_ceiling = current_year - 5
    rows: list[dict] = []
    for _, fac in facilities.iterrows():
        fac_id = fac["facility_id"]
        year = parse_year(fac.get("yearEstablished"))
        if year is None:
            rows.append(_row(fac_id, TestResult.INDETERMINATE, None))
            continue

        if year > current_year:
            rows.append(_row(fac_id, TestResult.FAIL,
                             {"year": year, "matched_term": None,
                              "reason": "future"}))
            continue
        if year < MIN_PLAUSIBLE_YEAR:
            rows.append(_row(fac_id, TestResult.FAIL,
                             {"year": year, "matched_term": None,
                              "reason": f"before-{MIN_PLAUSIBLE_YEAR}"}))
            continue

        matched = claims_high_acuity(fac.get("capability"), fac.get("description"))
        if year > high_acuity_ceiling and matched is not None:
            rows.append(_row(fac_id, TestResult.FAIL,
                             {"year": year, "matched_term": matched,
                              "reason": f"post-{high_acuity_ceiling}-high-acuity"}))
            continue

        rows.append(_row(fac_id, TestResult.PASS, {"year": year, "matched_term": None}))

    return pd.DataFrame(rows)


def _row(fac_id: str, result: TestResult, evidence_ref: dict | None) -> dict:
    return {
        "facility_id": fac_id,
        "test_name": TestName.TEMPORAL.value,
        "result": result.value,
        "evidence_ref": evidence_ref,
    }
