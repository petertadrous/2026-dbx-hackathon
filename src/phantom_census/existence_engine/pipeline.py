"""Pipeline — orchestrate all six tests + Layer B + Adjudicator + Layer A + Layer C.

Implements EE-PIPE-001..004.

Order per `existence-engine-design.md § Layer ordering`:
    Tests 1–6 → Layer B → Adjudicator → Layer A → Layer C

The AI Evidence Layer is NOT invoked here; it runs lazily on planner-open
per EE-AI-001. The pipeline persists `ai_recommendation = NULL` and the
contested verdict; the planner-workspace fires `ai_evidence_layer.maybe_render`
when the side panel opens.

Output is filesystem (Parquet) by default; Lakebase load is owned by the
sibling lakebase-persistence segment.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd

from datasketch import MinHash

from . import embedding_drift, layer_a, layer_b, layer_c, nfhs, pin_lookup, spatial, temporal
from .adjudicator import run_adjudicator
from .data_loading import build_district_to_state
from .minhash import persist_signatures, run_minhash_test


@dataclass
class EngineInputs:
    facilities: pd.DataFrame
    india_post: pd.DataFrame
    nfhs: pd.DataFrame
    districts: gpd.GeoDataFrame
    hfr: pd.DataFrame
    district_to_state: dict[str, str] | None = None
    current_year: int | None = None
    snapshot_id: str = ""
    reconciliation_table: pd.DataFrame | None = None
    prior_embeddings: dict[str, bytes] | None = None
    nfhs_staff: pd.DataFrame | None = None


@dataclass
class EngineOutputs:
    facility_existence_tests: pd.DataFrame
    phantom_verdicts: pd.DataFrame
    claim_minhash_signatures: dict[str, MinHash]
    description_embeddings: dict[str, bytes] = field(default_factory=dict)
    facility_district_map: dict[str, str] = field(default_factory=dict)
    facility_capabilities: dict[str, list[str]] = field(default_factory=dict)
    snapshot_id: str = ""


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


# @spec EE-PIPE-001, EE-PIPE-002, EE-PIPE-003, EE-HASH-001
def run_engine(inputs: EngineInputs, ran_at: datetime | None = None) -> EngineOutputs:
    ran_at = ran_at or datetime.now(tz=timezone.utc)

    district_to_state = inputs.district_to_state
    if not district_to_state:
        district_to_state = build_district_to_state(inputs.india_post, inputs.nfhs)

    current_year = inputs.current_year or ran_at.year

    pin_centroids = pin_lookup.build_pin_centroids(inputs.india_post)
    facilities_with_district = spatial.assign_districts(inputs.facilities, inputs.districts)

    signatures: dict[str, MinHash] = {}

    # Tests 1–5
    t1 = pin_lookup.run_pin_test(inputs.facilities, pin_centroids)
    t2 = run_minhash_test(inputs.facilities, signatures_out=signatures)
    t3 = spatial.run_spatial_test(inputs.facilities, inputs.districts, inputs.india_post)
    t4 = nfhs.run_nfhs_test(facilities_with_district, inputs.nfhs, district_to_state)
    t5 = temporal.run_temporal_test(inputs.facilities, current_year)

    # Test 6 — embedding drift (EE-EMBED-001..007).
    current_embeddings = _build_current_embeddings(inputs.facilities)
    prior = inputs.prior_embeddings or {}
    t6 = embedding_drift.run_embedding_test(inputs.facilities, current_embeddings, prior)

    facility_tests = pd.concat([t1, t2, t3, t4, t5, t6], ignore_index=True)
    facility_tests["ran_at"] = ran_at

    # Layer B — dataset-version reconciliation, pre-Adjudicator.
    reconciliation = inputs.reconciliation_table
    if reconciliation is None:
        reconciliation = _empty(["pin_district", "spatial_district", "reason"])
    facility_tests = layer_b.run_layer_b(facility_tests, inputs.facilities, reconciliation)
    # Make sure any new override rows carry `ran_at` for the EE-ADJ-002 latest-by-ran_at rule.
    facility_tests["ran_at"] = facility_tests["ran_at"].fillna(ran_at)

    # Deterministic Adjudicator — six tests + Layer B overrides.
    verdicts = run_adjudicator(facility_tests)

    # Layer A inputs: facilities frame must carry `facility_name` and `district`.
    facilities_with_name = inputs.facilities.copy()
    if "facility_name" not in facilities_with_name.columns:
        facilities_with_name["facility_name"] = None
    if "district" not in facilities_with_name.columns:
        facilities_with_name = facilities_with_name.merge(
            facilities_with_district[["facility_id", "spatial_district"]],
            on="facility_id", how="left",
        ).rename(columns={"spatial_district": "district"})

    nfhs_staff_df = inputs.nfhs_staff if inputs.nfhs_staff is not None \
        else _empty(["district", "staff_name"])

    # Layer A — structured-field corroboration, post-Adjudicator.
    verdicts = layer_a.run_layer_a(verdicts, facilities_with_name, inputs.hfr, nfhs_staff_df)

    # Layer C — FMA corroboration synthesis (activation-gated to contested).
    # The pipeline injects a deterministic template-fallback ai_query by default
    # so batch runs do not hit the FMA; callers may swap in a real adapter.
    verdicts = layer_c.run_layer_c(
        verdicts, facilities_with_name, _empty(["facility_id", "matched", "reason"]),
        ai_query=_default_layer_c_ai_query,
    )

    verdicts["ran_at"] = ran_at
    # EE-AI cache columns initialized null at batch time; populated lazily at
    # planner-open time per EE-AI-001..012.
    if "ai_recommendation" not in verdicts.columns:
        verdicts["ai_recommendation"] = None
    if "ai_recommendation_evidence_state" not in verdicts.columns:
        verdicts["ai_recommendation_evidence_state"] = None
    if "override_id" not in verdicts.columns:
        verdicts["override_id"] = None

    fdm_df = facilities_with_district.dropna(subset=["district_id"])
    facility_district_map = dict(zip(fdm_df["facility_id"], fdm_df["district_id"]))

    facility_capabilities = _extract_facility_capabilities(inputs.facilities)

    return EngineOutputs(
        facility_existence_tests=facility_tests,
        phantom_verdicts=verdicts,
        claim_minhash_signatures=signatures,
        description_embeddings=current_embeddings,
        facility_district_map=facility_district_map,
        facility_capabilities=facility_capabilities,
        snapshot_id=inputs.snapshot_id,
    )


def _extract_facility_capabilities(facilities: pd.DataFrame) -> dict[str, list[str]]:
    """Per-facility capability claims, normalized to a list of lowercase strings.

    Read from `vf_facilities.capability` (array or comma-delimited string).
    Empty / missing → empty list (the facility participates in no
    `(district_id, capability)` desert_scores rows).
    """
    out: dict[str, list[str]] = {}
    if "capability" not in facilities.columns:
        return out
    for _, fac in facilities.iterrows():
        raw = fac.get("capability")
        if raw is None:
            continue
        if isinstance(raw, (list, tuple)):
            items = [str(x) for x in raw if x is not None]
        elif isinstance(raw, str):
            items = [c.strip() for c in raw.split(",") if c.strip()]
        else:
            items = [str(raw)]
        items = [c.lower().strip() for c in items if c]
        if items:
            out[fac["facility_id"]] = sorted(set(items))
    return out


def _build_current_embeddings(facilities: pd.DataFrame) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for _, fac in facilities.iterrows():
        blob = embedding_drift.compute_embedding(fac.get("description"))
        if blob is not None:
            out[fac["facility_id"]] = blob
    return out


def _default_layer_c_ai_query(**_kwargs) -> dict:
    """Template-only default. Real adapter injected by the batch entry point.

    Returning a non-dict here would trip Layer C's fallback path; instead we
    raise so the explicit EE-LAYER-C-004 template fallback fires.
    """
    raise NotImplementedError("Real FMA adapter must be injected by the batch entry point")


# @spec EE-HASH-001, EE-PIPE-002, EE-PIPE-003
def write_outputs(outputs: EngineOutputs, out_dir: Path) -> None:
    """Write engine outputs to a local Parquet cache.

    Files written:
      facility_existence_tests.parquet  — long-format test results (incl. layer-b overrides)
      phantom_verdicts.parquet          — one row per facility verdict (dual-verdict)
      claim_minhash.parquet             — BYTEA cache (EE-HASH-001)
      description_embeddings.parquet    — BYTEA cache (EE-EMBED-001, snapshot-scoped)
      facility_district_xref.csv        — facility_id → district_id (shapeID xref)

    Lakebase load is the lakebase-persistence segment's responsibility.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs.facility_existence_tests.to_parquet(out_dir / "facility_existence_tests.parquet")
    outputs.phantom_verdicts.to_parquet(out_dir / "phantom_verdicts.parquet")
    persist_signatures(outputs.claim_minhash_signatures, out_dir / "claim_minhash.parquet")
    pd.DataFrame(
        [{"facility_id": fid, "embedding_bytea": blob, "snapshot_id": outputs.snapshot_id}
         for fid, blob in outputs.description_embeddings.items()]
    ).to_parquet(out_dir / "description_embeddings.parquet")
    pd.DataFrame(
        [{"facility_id": fid, "district_id": did}
         for fid, did in outputs.facility_district_map.items()]
    ).to_csv(out_dir / "facility_district_xref.csv", index=False)
