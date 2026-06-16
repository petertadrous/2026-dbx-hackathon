"""Adjudicator — collapse six test outcomes to a single verdict.

Precedence per EE-ADJ-003/004/005/006/007:
  1. insufficient evidence  (testable < 2)   → contested/insufficient-evidence
  2. veto-fail              (any veto FAIL)  → phantom
  3. majority-fail          (≥2 non-veto FAIL) → phantom
  4. single non-veto fail   (exactly 1 FAIL) → contested
  5. clean                  (0 FAIL, ≥2 PASS) → real

`not-applicable` is NOT testable. `indeterminate` is NOT testable. Only PASS
and FAIL count toward the testable floor.

Layer B override contract (EE-ADJ-002): when a row exists with
`test_name = layer-b-override-pin` or `layer-b-override-spatial`, the
Adjudicator consumes the override row in place of the original `pin-reverse-lookup`
or `spatial-district-mismatch` row for the same `facility_id`. The original
row is retained for audit. When multiple override rows share a key, the row
with the latest `ran_at` is consumed (EE-Q1 resolution: re-batch policy is
latest-by-ran_at).

Output (EE-ADJ-008/009):
  * `adjudicator_verdict` — the deterministic Adjudicator's output; immutable
    downstream.
  * `verdict` — at Adjudicator-write time equals `adjudicator_verdict`; Layer A
    and planner override may mutate it later.
  * `test_outcome_vector` — full 6-test outcome vector as JSONB-shaped list.
"""
from __future__ import annotations

import pandas as pd

from .types import (
    LAYER_B_OVERRIDE_PIN,
    LAYER_B_OVERRIDE_SPATIAL,
    VETO_TESTS,
    TestName,
    TestResult,
    Verdict,
)

TESTABLE_FLOOR = 2

# Map override test names to the original they supersede.
_OVERRIDE_TO_ORIGINAL = {
    LAYER_B_OVERRIDE_PIN: TestName.PIN_LOOKUP.value,
    LAYER_B_OVERRIDE_SPATIAL: TestName.SPATIAL.value,
}


def _is_veto(test_name: str) -> bool:
    try:
        return TestName(test_name) in VETO_TESTS
    except ValueError:
        return False


# @spec EE-ADJ-003, EE-ADJ-004, EE-ADJ-005, EE-ADJ-006, EE-ADJ-007
def adjudicate_one(test_outcomes: list[dict]) -> dict:
    fails = [o for o in test_outcomes if o["result"] == TestResult.FAIL.value]
    passes = [o for o in test_outcomes if o["result"] == TestResult.PASS.value]
    testable = [
        o for o in test_outcomes
        if o["result"] in {TestResult.PASS.value, TestResult.FAIL.value}
    ]

    # EE-ADJ-003 — insufficient evidence beats veto.
    if len(testable) < TESTABLE_FLOOR:
        return {
            "verdict": Verdict.CONTESTED.value,
            "reason": "insufficient-evidence",
            "test_outcome_vector": test_outcomes,
        }

    if any(_is_veto(o["test_name"]) for o in fails):
        return {
            "verdict": Verdict.PHANTOM.value,
            "reason": "veto-fail",
            "test_outcome_vector": test_outcomes,
        }

    non_veto_fails = [o for o in fails if not _is_veto(o["test_name"])]

    if len(non_veto_fails) >= 2:
        return {
            "verdict": Verdict.PHANTOM.value,
            "reason": "majority-fail",
            "test_outcome_vector": test_outcomes,
        }

    if len(non_veto_fails) == 1:
        return {
            "verdict": Verdict.CONTESTED.value,
            "reason": "single-non-veto-fail",
            "test_outcome_vector": test_outcomes,
        }

    if len(fails) == 0 and len(passes) >= 2:
        return {
            "verdict": Verdict.REAL.value,
            "reason": None,
            "test_outcome_vector": test_outcomes,
        }

    # Catch-all (shouldn't happen if testable ≥ 2 is already established).
    return {
        "verdict": Verdict.CONTESTED.value,
        "reason": "indeterminate-mix",
        "test_outcome_vector": test_outcomes,
    }


def _consume_overrides(group: pd.DataFrame) -> list[dict]:
    """Resolve Layer B overrides per EE-ADJ-002.

    For each (facility_id, test_name) the Adjudicator consumes the row with
    MAX(ran_at). Override rows supersede their original. The original is
    retained in `facility_existence_tests` for audit but not consumed here.
    """
    # Pick the latest row per (test_name, facility_id) — if `ran_at` is present,
    # use it; otherwise default to the last seen row.
    use_ran_at = "ran_at" in group.columns
    latest: dict[str, dict] = {}
    if use_ran_at:
        sorted_group = group.sort_values("ran_at", kind="mergesort")
    else:
        sorted_group = group
    for _, r in sorted_group.iterrows():
        latest[r["test_name"]] = r.to_dict()

    # Override rows replace originals.
    for override_name, original_name in _OVERRIDE_TO_ORIGINAL.items():
        if override_name in latest:
            override_row = latest.pop(override_name)
            override_row["test_name"] = original_name
            latest[original_name] = override_row

    return [
        {
            "test_name": r["test_name"],
            "result": r["result"],
            "evidence_ref": r.get("evidence_ref"),
        }
        for r in latest.values()
    ]


# @spec EE-ADJ-001, EE-ADJ-002, EE-ADJ-008, EE-ADJ-009
def run_adjudicator(test_results: pd.DataFrame) -> pd.DataFrame:
    """Reduce long-format test outcomes to one verdict row per facility.

    Writes dual-verdict columns: `adjudicator_verdict` (immutable) and `verdict`
    (initialized equal; mutable by Layer A and planner override downstream).
    """
    rows: list[dict] = []
    for fac_id, grp in test_results.groupby("facility_id"):
        outcomes = _consume_overrides(grp)
        decision = adjudicate_one(outcomes)
        rows.append({
            "facility_id": fac_id,
            "adjudicator_verdict": decision["verdict"],
            "verdict": decision["verdict"],
            "reason": decision["reason"],
            "test_outcome_vector": decision["test_outcome_vector"],
            "rescue_applied": None,
            "layer_c_synthesis": None,
        })
    return pd.DataFrame(rows)
