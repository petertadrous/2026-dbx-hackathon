"""Shared types for the existence engine.

A test outcome is one of {pass, fail, indeterminate, not-applicable}.

A `verdict` from the deterministic Adjudicator is one of {phantom, real,
contested}; after planner override the `verdict` column may also take
`force-real-planner` or `force-phantom-planner`.

The six Prosecutor tests each produce one TestOutcome per facility.
The Adjudicator collapses the outcome vector to an `adjudicator_verdict`
(immutable). Layer A may patch the final `verdict` from `phantom` to
`contested` if rescue signals fire. The planner override path may mutate
`verdict` further. `adjudicator_verdict` is preserved unchanged for audit.
"""
from __future__ import annotations

from enum import Enum


class TestResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INDETERMINATE = "indeterminate"
    NOT_APPLICABLE = "not-applicable"


class Verdict(str, Enum):
    PHANTOM = "phantom"
    REAL = "real"
    CONTESTED = "contested"


# Planner-override verdict values (LP-SCHEMA-VERDICT-002).
FORCE_REAL_PLANNER = "force-real-planner"
FORCE_PHANTOM_PLANNER = "force-phantom-planner"


class TestName(str, Enum):
    PIN_LOOKUP = "pin-reverse-lookup"
    MINHASH = "minhash-near-duplicate"
    SPATIAL = "spatial-district-mismatch"
    NFHS = "nfhs-outcome-inconsistency"
    TEMPORAL = "temporal-implausibility"
    EMBEDDING = "embedding-drift"


# Layer B override test names — written to facility_existence_tests; consumed
# by the Adjudicator in place of the original PIN / spatial rows.
LAYER_B_OVERRIDE_PIN = "layer-b-override-pin"
LAYER_B_OVERRIDE_SPATIAL = "layer-b-override-spatial"


VETO_TESTS = frozenset({TestName.PIN_LOOKUP, TestName.SPATIAL})
