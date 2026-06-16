"""Test 6 — Embedding-Drift Cosine (supporting).

Implements EE-EMBED-001..007.

* `compute_embedding(text)` — deterministic 384-dim float32 vector per snapshot;
  returns the BYTEA-serializable bytes (float32 little-endian) the cache table
  writes. Verdict-time math at this layer is pure cosine — no LLM call.
* `run_embedding_test(facilities, current, prior)` — emits the Test 6 outcome
  rows the pipeline concatenates with Tests 1–5.
* `is_valid_snapshot_id(s)` — checks the `YYYY-MM-DD-batch-NNN` schema.

Encoder choice (production): `all-MiniLM-L6-v2` via the Foundation Model API or
a local sentence-transformer. Tests inject vectors directly to avoid loading a
model in unit-test runs.
"""
from __future__ import annotations

import hashlib
import re
import struct

import numpy as np
import pandas as pd

from .types import TestName, TestResult


EMBEDDING_DIM = 384
DRIFT_FAIL_THRESHOLD = 0.4  # cosine drift = 1 − cosine_similarity
MIN_TOKENS = 30

_SNAPSHOT_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-batch-\d{3}$")


# @spec EE-EMBED-001
def is_valid_snapshot_id(s: object) -> bool:
    """Validate the YYYY-MM-DD-batch-NNN snapshot identifier format."""
    if not isinstance(s, str):
        return False
    return bool(_SNAPSHOT_ID_RE.fullmatch(s))


# @spec EE-EMBED-001, EE-EMBED-006
def compute_embedding(text: object) -> bytes | None:
    """Produce a deterministic 384-dim float32 embedding for a description.

    Returns the BYTEA bytes the cache.description_embeddings table stores.
    Returns None when the description is absent or has fewer than MIN_TOKENS
    tokens (EE-EMBED-006).

    Production path uses a sentence-transformer; this fallback is a hashed
    pseudo-embedding suitable for offline determinism + unit tests. The
    contract — input text → 384 float32 bytes — is the same either way.
    """
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    if len(s.split()) < MIN_TOKENS:
        return None
    # Deterministic 384-dim pseudo-vector seeded from the text hash.
    seed = int.from_bytes(hashlib.sha256(s.encode("utf-8")).digest()[:8], "little")
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
    norm = np.linalg.norm(v)
    if norm > 0:
        v = v / norm
    return v.tobytes()


def _to_vector(blob: bytes | None) -> np.ndarray | None:
    if blob is None:
        return None
    arr = np.frombuffer(blob, dtype=np.float32)
    if arr.size != EMBEDDING_DIM:
        return None
    return arr


# @spec EE-EMBED-002, EE-EMBED-003, EE-EMBED-004, EE-EMBED-005, EE-EMBED-007
def run_embedding_test(
    facilities: pd.DataFrame,
    current_embeddings: dict[str, bytes],
    prior_embeddings: dict[str, bytes],
) -> pd.DataFrame:
    """Emit per-facility Test 6 outcome rows.

    `current_embeddings` and `prior_embeddings` map facility_id → BYTEA bytes.
    A facility with no prior or no current embedding → indeterminate
    (EE-EMBED-005). On a first batch (`prior_embeddings == {}`), every facility
    is indeterminate (EE-EMBED-007).
    """
    rows: list[dict] = []
    for _, fac in facilities.iterrows():
        fac_id = fac["facility_id"]
        cur_vec = _to_vector(current_embeddings.get(fac_id))
        prior_vec = _to_vector(prior_embeddings.get(fac_id))

        if cur_vec is None or prior_vec is None:
            rows.append(_row(fac_id, TestResult.INDETERMINATE, None))
            continue

        cos = float(np.dot(cur_vec, prior_vec))
        cos = max(-1.0, min(1.0, cos))
        drift = 1.0 - cos
        if drift >= DRIFT_FAIL_THRESHOLD:
            rows.append(_row(fac_id, TestResult.FAIL, {
                "cosine_drift": drift,
                "threshold": DRIFT_FAIL_THRESHOLD,
            }))
        else:
            rows.append(_row(fac_id, TestResult.PASS, None))

    return pd.DataFrame(rows)


def _row(fac_id: str, result: TestResult, evidence_ref: dict | None) -> dict:
    return {
        "facility_id": fac_id,
        "test_name": TestName.EMBEDDING.value,
        "result": result.value,
        "evidence_ref": evidence_ref,
    }


# @spec EE-EMBED-001 — serialization helper for the cache.description_embeddings
# loader. Returns identity bytes; kept as a named function so the lakebase loader
# imports a single, documented symbol.
def serialize_embedding(blob: bytes) -> bytes:
    return blob


# Reserved for future numpy-array path — kept here so callers don't need to
# import struct or numpy directly.
def vector_to_bytes(v: np.ndarray) -> bytes:
    return np.asarray(v, dtype=np.float32).tobytes()


def bytes_to_vector(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)


# Silence unused-import lint without affecting public API.
_ = struct
