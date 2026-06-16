"""Pure unit tests for lakebase writer — no database required.

These catch data-cleaning bugs (null bytes, encoding issues) by mocking the
SQLAlchemy engine and asserting on what rows would have been sent to Postgres.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest
from datasketch import MinHash

from phantom_census.existence_engine.pipeline import EngineOutputs
from phantom_census.lakebase.writer import _strip_nul, load_engine_outputs


# ── helper ────────────────────────────────────────────────────────────────────

def _make_engine():
    """Return (mock_engine, mock_conn) where begin() is a proper context mgr."""
    mock_conn = MagicMock()
    mock_engine = MagicMock()

    @contextmanager
    def _begin():
        yield mock_conn

    mock_engine.begin = _begin
    return mock_engine, mock_conn


def _all_string_values(mock_conn) -> list[str]:
    """Collect every string value passed to conn.execute across all calls."""
    result = []
    for call in mock_conn.execute.call_args_list:
        args = call[0]
        if len(args) < 2:
            continue
        rows = args[1] if isinstance(args[1], list) else [args[1]]
        for row in rows:
            vals = row.values() if isinstance(row, dict) else []
            for v in vals:
                if isinstance(v, str):
                    result.append(v)
    return result


def _minimal_outputs(
    facility_id: str = "F1",
    verdict: str = "real",
    reason: str | None = None,
    test_result: str = "pass",
) -> EngineOutputs:
    ran_at = datetime(2026, 6, 15, tzinfo=timezone.utc)
    m = MinHash(num_perm=128)
    m.update(b"token")
    return EngineOutputs(
        facility_existence_tests=pd.DataFrame([{
            "facility_id": facility_id,
            "test_name": "pin-reverse-lookup",
            "result": test_result,
            "evidence_ref": None,
            "ran_at": ran_at,
        }]),
        phantom_verdicts=pd.DataFrame([{
            "facility_id": facility_id,
            "verdict": verdict,
            "reason": reason,
            "test_outcome_vector": [],
            "ran_at": ran_at,
        }]),
        claim_minhash_signatures={facility_id: m},
    )


# ── _strip_nul ────────────────────────────────────────────────────────────────

def test_strip_nul_removes_embedded_nul():
    assert _strip_nul("fo\x00o") == "foo"

def test_strip_nul_removes_multiple_nuls():
    assert _strip_nul("\x00a\x00b\x00") == "ab"

def test_strip_nul_passthrough_clean_string():
    assert _strip_nul("clean") == "clean"

def test_strip_nul_none_passthrough():
    assert _strip_nul(None) is None


# ── load_engine_outputs — null byte stripping ─────────────────────────────────

def test_writer_strips_nul_from_reason(monkeypatch):
    """Null bytes in verdict.reason must be stripped before reaching Postgres."""
    engine, conn = _make_engine()
    outputs = _minimal_outputs(reason="veto\x00fail")
    load_engine_outputs(outputs, engine, ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    strings = _all_string_values(conn)
    assert any("vetofail" in s for s in strings), "stripped reason not found"
    assert not any("\x00" in s for s in strings), "null byte survived into execute()"


def test_writer_strips_nul_from_test_result(monkeypatch):
    """Null bytes in existence_test.result must be stripped."""
    engine, conn = _make_engine()
    outputs = _minimal_outputs(test_result="pa\x00ss")
    load_engine_outputs(outputs, engine, ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    strings = _all_string_values(conn)
    assert not any("\x00" in s for s in strings), "null byte survived into execute()"


def test_writer_strips_nul_from_facility_id(monkeypatch):
    """Null bytes in facility_id (however unlikely) must be stripped."""
    engine, conn = _make_engine()
    outputs = _minimal_outputs(facility_id="F\x001")
    load_engine_outputs(outputs, engine, ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    strings = _all_string_values(conn)
    assert not any("\x00" in s for s in strings), "null byte survived into execute()"


def test_writer_called_twice_with_same_facility_id_no_duplicate(monkeypatch):
    """Same facility_id appearing in both verdicts and tests must not cause a
    duplicate-key error — guards against the noisy VF dataset where unique_id
    is not enforced unique."""
    engine, conn = _make_engine()
    ran_at = datetime(2026, 6, 15, tzinfo=timezone.utc)
    m = MinHash(num_perm=128)
    m.update(b"x")

    # Two rows for the same facility_id (mirrors the VF dataset duplication)
    verdicts = pd.DataFrame([
        {"facility_id": "DUP1", "verdict": "real",    "reason": None, "test_outcome_vector": [], "ran_at": ran_at},
        {"facility_id": "DUP1", "verdict": "phantom", "reason": "copy", "test_outcome_vector": [], "ran_at": ran_at},
    ])
    tests = pd.DataFrame([
        {"facility_id": "DUP1", "test_name": "pin-reverse-lookup", "result": "pass", "evidence_ref": None, "ran_at": ran_at},
        {"facility_id": "DUP1", "test_name": "pin-reverse-lookup", "result": "fail", "evidence_ref": None, "ran_at": ran_at},
    ])
    outputs = EngineOutputs(
        facility_existence_tests=tests,
        phantom_verdicts=verdicts,
        claim_minhash_signatures={"DUP1": m},
    )
    # Should not raise — writer deduplicates or uses ON CONFLICT
    load_engine_outputs(outputs, engine, ran_at=ran_at)


def test_clean_data_passes_through_unchanged():
    """Ensure the stripping logic doesn't mutate clean values."""
    engine, conn = _make_engine()
    outputs = _minimal_outputs(reason="legit-reason", test_result="pass")
    load_engine_outputs(outputs, engine, ran_at=datetime(2026, 6, 15, tzinfo=timezone.utc))
    strings = _all_string_values(conn)
    assert any("legit-reason" in s for s in strings)
    assert any("pass" in s for s in strings)
