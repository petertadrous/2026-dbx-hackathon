"""Test 2 — MinHash near-duplicate detection (supporting).

Implements EE-HASH-001..005.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from datasketch import MinHash

from .types import TestName, TestResult

NUM_PERMUTATIONS = 128
SHINGLE_SIZE = 5
JACCARD_THRESHOLD = 0.9
MIN_TOKENS = 30
MIN_CLUSTER_SIZE = 3


def _flatten(field: object) -> str:
    if field is None:
        return ""
    if isinstance(field, (list, tuple)):
        return " ".join(str(x) for x in field if x is not None)
    return str(field)


def build_claim_text(row: pd.Series) -> str:
    parts = [
        _flatten(row.get("capability")),
        _flatten(row.get("procedure")),
        _flatten(row.get("equipment")),
    ]
    return " ".join(p for p in parts if p).strip()


def _shingles(text: str, k: int) -> set[str]:
    text = text.lower()
    if len(text) < k:
        return set()
    return {text[i : i + k] for i in range(len(text) - k + 1)}


# @spec EE-HASH-001, EE-HASH-002
def compute_minhash(text: str) -> MinHash | None:
    if not text or len(text.split()) < MIN_TOKENS:
        return None
    shingles = _shingles(text, SHINGLE_SIZE)
    if not shingles:
        return None
    m = MinHash(num_perm=NUM_PERMUTATIONS)
    for s in shingles:
        m.update(s.encode("utf-8"))
    return m


# @spec EE-HASH-003
def cluster_by_jaccard(signatures: dict[str, MinHash]) -> dict[str, list[str]]:
    """Connected-component flood-fill: pairwise Jaccard ≥ threshold → same cluster.

    O(n^2) — acceptable for 10k facilities (50M comparisons, ~30s).
    """
    ids = list(signatures.keys())
    parent = {i: i for i in ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            if signatures[a].jaccard(signatures[b]) >= JACCARD_THRESHOLD:
                union(a, b)

    clusters: dict[str, list[str]] = {}
    for fid in ids:
        root = find(fid)
        clusters.setdefault(root, []).append(fid)

    return {fid: clusters[find(fid)] for fid in ids}


# @spec EE-HASH-001
def serialize_signature(sig: MinHash) -> bytes:
    """Serialize a MinHash signature to BYTEA-compatible bytes (uint32 hash values).

    A 128-perm signature is 512 bytes (128 × 4-byte uint32).
    """
    return np.asarray(sig.hashvalues, dtype=np.uint32).tobytes()


# @spec EE-HASH-001, EE-HASH-002, EE-HASH-003, EE-HASH-004, EE-HASH-005
def run_minhash_test(
    facilities: pd.DataFrame,
    signatures_out: dict[str, MinHash] | None = None,
) -> pd.DataFrame:
    """Run Test 2; optionally capture computed signatures into `signatures_out`.

    Callers wanting to persist EE-HASH-001's BYTEA cache pass a dict; it is
    filled with {facility_id: MinHash}. Use `serialize_signature()` to get
    BYTEA bytes per facility.
    """
    signatures: dict[str, MinHash] = {}
    indeterminate: list[str] = []

    for _, fac in facilities.iterrows():
        fac_id = fac["facility_id"]
        text = build_claim_text(fac)
        sig = compute_minhash(text)
        if sig is None:
            indeterminate.append(fac_id)
        else:
            signatures[fac_id] = sig

    if signatures_out is not None:
        signatures_out.update(signatures)

    cluster_map = cluster_by_jaccard(signatures) if signatures else {}

    rows: list[dict] = []
    for fac_id in indeterminate:
        rows.append(_row(fac_id, TestResult.INDETERMINATE, None))

    for fac_id, members in cluster_map.items():
        if len(members) >= MIN_CLUSTER_SIZE:
            rows.append(_row(fac_id, TestResult.FAIL, {
                "cluster_size": len(members),
                "cluster_member_ids": sorted(members),
            }))
        else:
            rows.append(_row(fac_id, TestResult.PASS, None))

    out = pd.DataFrame(rows)
    if not out.empty:
        order = list(facilities["facility_id"])
        out["__sort"] = out["facility_id"].map({fid: i for i, fid in enumerate(order)})
        out = out.sort_values("__sort").drop(columns="__sort").reset_index(drop=True)
    return out


# @spec EE-HASH-001
def persist_signatures(signatures: dict[str, MinHash], out_path: Path) -> None:
    """Write {facility_id, signature_bytea} to a Parquet cache.

    Lakebase load (cache.claim_minhash, naming aligned with lakebase-persistence
    LLD) is owned by the sibling segment; this writes the local cache file the
    Lakebase loader reads.
    """
    rows = [
        {"facility_id": fid, "signature_bytea": serialize_signature(sig)}
        for fid, sig in signatures.items()
    ]
    df = pd.DataFrame(rows, columns=["facility_id", "signature_bytea"])
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)


def _row(fac_id: str, result: TestResult, evidence_ref: dict | None) -> dict:
    return {
        "facility_id": fac_id,
        "test_name": TestName.MINHASH.value,
        "result": result.value,
        "evidence_ref": evidence_ref,
    }
