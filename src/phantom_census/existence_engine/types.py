"""Shared types for the existence engine.

A test outcome is one of {pass, fail, indeterminate, not-applicable}.
A verdict is one of {phantom, real, contested}.

The five Prosecutor tests each produce one TestOutcome per facility.
The Adjudicator collapses the outcome vector to a Verdict.
The Defender may upgrade `phantom` to `contested` post-Adjudicator.
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


class TestName(str, Enum):
    PIN_LOOKUP = "pin-reverse-lookup"
    MINHASH = "minhash-near-duplicate"
    SPATIAL = "spatial-district-mismatch"
    NFHS = "nfhs-outcome-inconsistency"
    TEMPORAL = "temporal-implausibility"
    DEFENDER_RESCUE = "defender-rescue"


VETO_TESTS = frozenset({TestName.PIN_LOOKUP, TestName.SPATIAL})
