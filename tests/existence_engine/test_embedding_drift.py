"""Tests for Test 6 — Embedding-Drift Cosine.

Covers EE-EMBED-001..007.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from phantom_census.existence_engine import embedding_drift
from phantom_census.existence_engine.types import TestName, TestResult


EMBEDDING_DIM = 384


def _vec(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
    return v / np.linalg.norm(v)


def _serialize(v: np.ndarray) -> bytes:
    return np.asarray(v, dtype=np.float32).tobytes()


# @spec EE-EMBED-001
def test_compute_embedding_returns_384_dim_bytea():
    """Encoder produces 384-dim float32 vectors stored as BYTEA."""
    desc = (
        "Multi-specialty hospital in Mumbai with maternity, NICU, ICU, "
        "and 24/7 emergency services. Long description of services."
    ) * 2
    blob = embedding_drift.compute_embedding(desc)
    assert isinstance(blob, (bytes, bytearray))
    arr = np.frombuffer(blob, dtype=np.float32)
    assert arr.shape == (EMBEDDING_DIM,)


# @spec EE-EMBED-005
def test_compute_embedding_returns_none_when_description_too_short():
    """EE-EMBED-006 says <30 tokens → indeterminate; encoder returns None."""
    assert embedding_drift.compute_embedding("a b c d e") is None
    assert embedding_drift.compute_embedding("") is None
    assert embedding_drift.compute_embedding(None) is None


# @spec EE-EMBED-002, EE-EMBED-004
def test_test6_pass_when_cosine_drift_below_threshold():
    """Same embedding in both snapshots → cosine drift = 0 → pass."""
    v = _vec(0)
    facilities = pd.DataFrame([{"facility_id": "F1"}])
    current = {"F1": _serialize(v)}
    prior = {"F1": _serialize(v)}
    out = embedding_drift.run_embedding_test(
        facilities, current_embeddings=current, prior_embeddings=prior,
    )
    row = out.iloc[0]
    assert row["test_name"] == TestName.EMBEDDING.value
    assert row["result"] == TestResult.PASS.value


# @spec EE-EMBED-003
def test_test6_fail_when_cosine_drift_at_or_above_threshold():
    """Orthogonal embedding → cosine similarity 0 → drift 1.0 → fail with evidence."""
    v_current = _vec(1)
    v_prior = _vec(2)
    facilities = pd.DataFrame([{"facility_id": "F1"}])
    current = {"F1": _serialize(v_current)}
    prior = {"F1": _serialize(v_prior)}
    out = embedding_drift.run_embedding_test(
        facilities, current_embeddings=current, prior_embeddings=prior,
    )
    row = out.iloc[0]
    assert row["result"] == TestResult.FAIL.value
    ev = row["evidence_ref"]
    assert "cosine_drift" in ev
    assert "threshold" in ev
    assert ev["cosine_drift"] >= 0.4


# @spec EE-EMBED-005
def test_test6_indeterminate_when_no_prior_snapshot():
    v = _vec(3)
    facilities = pd.DataFrame([{"facility_id": "F1"}])
    out = embedding_drift.run_embedding_test(
        facilities,
        current_embeddings={"F1": _serialize(v)},
        prior_embeddings={},
    )
    assert out.iloc[0]["result"] == TestResult.INDETERMINATE.value


# @spec EE-EMBED-005
def test_test6_indeterminate_when_no_current_snapshot():
    v = _vec(4)
    facilities = pd.DataFrame([{"facility_id": "F1"}])
    out = embedding_drift.run_embedding_test(
        facilities,
        current_embeddings={},
        prior_embeddings={"F1": _serialize(v)},
    )
    assert out.iloc[0]["result"] == TestResult.INDETERMINATE.value


# @spec EE-EMBED-007
def test_test6_first_batch_returns_indeterminate_for_every_facility():
    facilities = pd.DataFrame([{"facility_id": fid} for fid in ("F1", "F2", "F3")])
    current = {fid: _serialize(_vec(i)) for i, fid in enumerate(("F1", "F2", "F3"))}
    out = embedding_drift.run_embedding_test(
        facilities,
        current_embeddings=current,
        prior_embeddings={},  # no prior snapshot — first batch run
    )
    assert (out["result"] == TestResult.INDETERMINATE.value).all()


# @spec EE-EMBED-001
def test_snapshot_id_format_validates_yyyy_mm_dd_batch_nnn():
    """EE-EMBED-001: snapshot_id format is YYYY-MM-DD-batch-NNN."""
    assert embedding_drift.is_valid_snapshot_id("2026-06-15-batch-001")
    assert embedding_drift.is_valid_snapshot_id("2025-12-31-batch-999")
    assert not embedding_drift.is_valid_snapshot_id("2026-06-15")
    assert not embedding_drift.is_valid_snapshot_id("batch-001")
    assert not embedding_drift.is_valid_snapshot_id("2026-06-15-batch-1")
