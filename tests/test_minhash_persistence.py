"""Tests for EE-HASH-001 BYTEA signature cache.

The signature cache feeds the lakebase-persistence segment's cache.claim_minhash
table. This module verifies the local Parquet writer that the loader reads.
"""
from __future__ import annotations

import pandas as pd
from datasketch import MinHash

from phantom_census.existence_engine import minhash


def _long_claim(seed: str) -> dict:
    return {
        "capability": [
            f"Maternity ward {seed}", f"NICU level three {seed}",
            f"Obstetrics {seed}", f"Pediatric ICU {seed}",
            f"General surgery {seed}", f"Cardiology unit {seed}",
            f"Emergency dept {seed}", f"Internal medicine {seed}",
        ],
        "procedure": [
            f"Cesarean section {seed}", f"Vaginal delivery {seed}",
            f"Hysterectomy {seed}", f"Appendectomy {seed}",
            f"Tonsillectomy {seed}", f"Hernia repair {seed}",
        ],
        "equipment": [
            f"Mechanical ventilator {seed}", f"Ultrasound machine {seed}",
            f"MRI scanner {seed}", f"CT scanner {seed}",
            f"Incubator {seed}", f"Defibrillator {seed}",
        ],
    }


# @spec EE-HASH-001
def test_serialize_signature_is_bytes():
    m = MinHash(num_perm=128)
    m.update(b"hello world")
    out = minhash.serialize_signature(m)
    assert isinstance(out, bytes)
    assert len(out) == 128 * 4  # uint32 per permutation


# @spec EE-HASH-001
def test_serialize_signature_round_trip_preserves_jaccard():
    import numpy as np
    m1 = MinHash(num_perm=128)
    m2 = MinHash(num_perm=128)
    for tok in ("alpha", "beta", "gamma", "delta", "epsilon"):
        m1.update(tok.encode())
        m2.update(tok.encode())
    b1 = minhash.serialize_signature(m1)
    restored = MinHash(num_perm=128,
                       hashvalues=np.frombuffer(b1, dtype=np.uint32))
    assert restored.jaccard(m2) == 1.0


# @spec EE-HASH-001
def test_run_minhash_test_fills_signatures_out():
    facilities = pd.DataFrame([
        {"facility_id": "F1", **_long_claim("alpha")},
        {"facility_id": "F2", **_long_claim("beta")},
    ])
    sigs: dict = {}
    minhash.run_minhash_test(facilities, signatures_out=sigs)
    assert set(sigs.keys()) == {"F1", "F2"}
    assert all(isinstance(s, MinHash) for s in sigs.values())


# @spec EE-HASH-001
def test_persist_signatures_writes_parquet(tmp_path):
    facilities = pd.DataFrame([
        {"facility_id": "P1", **_long_claim("delta")},
        {"facility_id": "P2", **_long_claim("epsilon")},
    ])
    sigs: dict = {}
    minhash.run_minhash_test(facilities, signatures_out=sigs)
    out = tmp_path / "claim_minhash.parquet"
    minhash.persist_signatures(sigs, out)
    assert out.exists()
    df = pd.read_parquet(out)
    assert set(df.columns) == {"facility_id", "signature_bytea"}
    assert set(df["facility_id"]) == {"P1", "P2"}
    assert all(isinstance(b, (bytes, bytearray)) for b in df["signature_bytea"])
    assert (df["signature_bytea"].str.len() == 128 * 4).all()
