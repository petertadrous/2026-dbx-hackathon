"""Test 4 — NFHS-5 outcome inconsistency (supporting).

Implements EE-NFHS-001..005.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .spatial import normalize_district_name
from .types import TestName, TestResult

MATERNITY_TERMS = (
    "maternity",
    "nicu",
    "delivery",
    "obstetric",
    "antenatal",
    "postnatal",
    "c-section",
    "caesarean",
)

_MATERNITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in MATERNITY_TERMS) + r")\b",
    re.IGNORECASE,
)


def _join(field: object) -> str:
    if field is None:
        return ""
    if isinstance(field, (list, tuple)):
        return " ".join(str(x) for x in field if x is not None)
    return str(field)


# @spec EE-NFHS-001
def claims_maternity(capability: object, description: object) -> bool:
    text = (_join(capability) + " " + _join(description)).lower()
    return bool(_MATERNITY_RE.search(text))


# @spec EE-NFHS-002, EE-NFHS-003
def state_quartile_cutoffs(nfhs_df: pd.DataFrame) -> dict[str, float]:
    df = nfhs_df.copy()
    df["rate"] = pd.to_numeric(df["institutional_delivery_rate"], errors="coerce")
    df = df.dropna(subset=["rate"])
    cutoffs: dict[str, float] = {}
    for state, group in df.groupby("state"):
        cutoffs[state] = float(np.percentile(group["rate"], 25))
    return cutoffs


# @spec EE-NFHS-001..005
def run_nfhs_test(
    facilities: pd.DataFrame,
    nfhs_df: pd.DataFrame,
    district_to_state: dict[str, str],
) -> pd.DataFrame:
    cutoffs = state_quartile_cutoffs(nfhs_df)
    nfhs_lookup = (
        nfhs_df.dropna(subset=["district"])
        .copy()
    )
    nfhs_lookup["rate"] = pd.to_numeric(
        nfhs_lookup["institutional_delivery_rate"], errors="coerce"
    )
    # Normalize district keys to absorb spelling drift between datasets
    # (e.g. "Mysore"/"Mysuru", "Maharastra"/"Maharashtra").
    rate_by_district: dict[str, float | None] = {
        normalize_district_name(row["district"]): (
            None if pd.isna(row["rate"]) else float(row["rate"])
        )
        for _, row in nfhs_lookup.iterrows()
    }
    norm_district_to_state = {
        normalize_district_name(k): v for k, v in district_to_state.items()
    }

    rows: list[dict] = []
    for _, fac in facilities.iterrows():
        fac_id = fac["facility_id"]
        if not claims_maternity(fac.get("capability"), fac.get("description")):
            rows.append(_row(fac_id, TestResult.NOT_APPLICABLE, None))
            continue

        sp_district = fac.get("spatial_district")
        if sp_district is None:
            rows.append(_row(fac_id, TestResult.INDETERMINATE, None))
            continue
        norm_district = normalize_district_name(sp_district)
        if norm_district not in rate_by_district:
            rows.append(_row(fac_id, TestResult.INDETERMINATE, None))
            continue

        rate = rate_by_district[norm_district]
        if rate is None:
            rows.append(_row(fac_id, TestResult.INDETERMINATE, None))
            continue

        state = norm_district_to_state.get(norm_district)
        if state is None or state not in cutoffs:
            rows.append(_row(fac_id, TestResult.INDETERMINATE, None))
            continue

        cutoff = cutoffs[state]
        if rate < cutoff:
            rows.append(_row(fac_id, TestResult.FAIL, {
                "district_rate": rate, "state_cutoff": cutoff, "state": state,
            }))
        else:
            rows.append(_row(fac_id, TestResult.PASS, {
                "district_rate": rate, "state_cutoff": cutoff, "state": state,
            }))

    return pd.DataFrame(rows)


def _row(fac_id: str, result: TestResult, evidence_ref: dict | None) -> dict:
    return {
        "facility_id": fac_id,
        "test_name": TestName.NFHS.value,
        "result": result.value,
        "evidence_ref": evidence_ref,
    }
