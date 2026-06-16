"""Adjudicator — collapse 5 test outcomes to a single verdict.

Precedence per LLD + E1 resolution:
  1. insufficient evidence  (testable < 2)   → contested/insufficient-evidence
  2. veto-fail              (any veto FAIL)  → phantom
  3. majority-fail          (≥2 non-veto FAIL) → phantom
  4. single non-veto fail   (exactly 1 FAIL) → contested
  5. clean                  (0 FAIL, ≥2 PASS) → real

`not-applicable` is NOT testable (per E2 resolution).
`indeterminate` is NOT testable.

Implements EE-ADJ-001..007.
"""
from __future__ import annotations

import pandas as pd

from .types import VETO_TESTS, TestName, TestResult, Verdict

TESTABLE_FLOOR = 2


def _is_veto(test_name: str) -> bool:
    return TestName(test_name) in VETO_TESTS


# @spec EE-ADJ-001..006
def adjudicate_one(test_outcomes: list[dict]) -> dict:
    fails = [o for o in test_outcomes if o["result"] == TestResult.FAIL.value]
    passes = [o for o in test_outcomes if o["result"] == TestResult.PASS.value]
    testable = [
        o for o in test_outcomes
        if o["result"] in {TestResult.PASS.value, TestResult.FAIL.value}
    ]

    # Precedence rule 1: insufficient evidence beats everything else (E1).
    if len(testable) < TESTABLE_FLOOR:
        return {
            "verdict": Verdict.CONTESTED.value,
            "reason": "insufficient-evidence",
            "test_outcome_vector": test_outcomes,
        }

    veto_fail = any(_is_veto(o["test_name"]) for o in fails)
    non_veto_fails = [o for o in fails if not _is_veto(o["test_name"])]

    if veto_fail:
        return {
            "verdict": Verdict.PHANTOM.value,
            "reason": "veto-fail",
            "test_outcome_vector": test_outcomes,
        }

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

    # Catch-all (shouldn't happen if testable >= 2 already established)
    return {
        "verdict": Verdict.CONTESTED.value,
        "reason": "indeterminate-mix",
        "test_outcome_vector": test_outcomes,
    }


# @spec EE-ADJ-001, EE-ADJ-007
def run_adjudicator(test_results: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for fac_id, grp in test_results.groupby("facility_id"):
        outcomes = [
            {
                "test_name": r["test_name"],
                "result": r["result"],
                "evidence_ref": r.get("evidence_ref"),
            }
            for _, r in grp.iterrows()
        ]
        decision = adjudicate_one(outcomes)
        rows.append({
            "facility_id": fac_id,
            "verdict": decision["verdict"],
            "reason": decision["reason"],
            "test_outcome_vector": decision["test_outcome_vector"],
        })
    return pd.DataFrame(rows)
