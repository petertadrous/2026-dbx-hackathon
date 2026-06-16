"""Defender Layer B — dataset-version reconciliation (pre-Adjudicator).

Implements EE-LAYER-B-001..006.

Layer B runs before the Adjudicator. For each Test 1 (PIN) or Test 3 (spatial)
failure, it looks up the (pin_district, spatial_district) pair in a
deterministic reconciliation table covering post-2022 district reorganizations
and known spelling variants. When a match is found, Layer B writes a
`layer-b-override-pin` or `layer-b-override-spatial` row with `result = pass`
and an evidence_ref citing the matched reason. The originals are preserved
in `facility_existence_tests` for audit; the Adjudicator's input contract
consumes the override row in place of the original (EE-ADJ-002).
"""
from __future__ import annotations

import pandas as pd

from .types import LAYER_B_OVERRIDE_PIN, LAYER_B_OVERRIDE_SPATIAL, TestName, TestResult


def _norm(s: object) -> str:
    if s is None:
        return ""
    return str(s).strip().lower()


def _lookup(
    pin_district: str, spatial_district: str, table: pd.DataFrame,
) -> dict | None:
    """Find a reconciliation entry for a (pin, spatial) disagreement."""
    if table.empty:
        return None
    pin_n = _norm(pin_district)
    sp_n = _norm(spatial_district)
    for _, row in table.iterrows():
        if _norm(row.get("pin_district")) == pin_n and \
                _norm(row.get("spatial_district")) == sp_n:
            return {
                "matched": "pin_district + spatial_district",
                "reason": row.get("reason"),
            }
    return None


# @spec EE-LAYER-B-001, EE-LAYER-B-002, EE-LAYER-B-003, EE-LAYER-B-004,
# @spec EE-LAYER-B-005, EE-LAYER-B-006
def run_layer_b(
    test_results: pd.DataFrame,
    facilities: pd.DataFrame,  # noqa: ARG001 — accepted for symmetry with other layers
    reconciliation_table: pd.DataFrame,
) -> pd.DataFrame:
    """Append override rows for explained PIN / spatial failures.

    Returns the original frame with at most one `layer-b-override-pin` row and
    at most one `layer-b-override-spatial` row per facility appended; originals
    are preserved unchanged (EE-LAYER-B-004).
    """
    if test_results.empty:
        return test_results.copy()

    appended: list[dict] = []
    # Track (facility_id, family) to enforce at-most-one override per family
    # within a single Layer B run (EE-LAYER-B-005).
    seen: set[tuple[str, str]] = set()

    for _, row in test_results.iterrows():
        if row["result"] != TestResult.FAIL.value:
            continue
        tname = row["test_name"]
        if tname == TestName.PIN_LOOKUP.value:
            override_name = LAYER_B_OVERRIDE_PIN
            family = "pin"
        elif tname == TestName.SPATIAL.value:
            override_name = LAYER_B_OVERRIDE_SPATIAL
            family = "spatial"
        else:
            continue  # EE-LAYER-B-001 — only Test 1 / Test 3 are in scope

        key = (row["facility_id"], family)
        if key in seen:
            continue

        ev = row.get("evidence_ref") or {}
        pin_d = ev.get("pin_district") if isinstance(ev, dict) else None
        sp_d = ev.get("spatial_district") if isinstance(ev, dict) else None
        if not pin_d or not sp_d:
            continue

        match = _lookup(pin_d, sp_d, reconciliation_table)
        if match is None:
            continue  # EE-LAYER-B-006

        seen.add(key)
        appended.append({
            "facility_id": row["facility_id"],
            "test_name": override_name,
            "result": TestResult.PASS.value,
            "evidence_ref": match,
        })

    if not appended:
        return test_results.copy()

    extra_cols = [c for c in test_results.columns
                  if c not in {"facility_id", "test_name", "result", "evidence_ref"}]
    for r in appended:
        for c in extra_cols:
            r.setdefault(c, None)

    return pd.concat(
        [test_results, pd.DataFrame(appended)],
        ignore_index=True,
    )
