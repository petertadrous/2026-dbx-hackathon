# Databricks notebook source
# Run on DBR 15.4 LTS ML (includes geopandas system libs).
# Reads bronze UC tables → runs the 6-test existence engine → writes gold Delta tables.
# Gold tables are then mirrored to Lakebase as synced tables via
# `databricks postgres create-synced-table` per LP-SYNC-001..LP-SYNC-006.

# COMMAND ----------

# MAGIC %pip install --quiet \
# MAGIC   "git+https://github.com/petertadrous/2026-dbx-hackathon.git@updated-specs" \
# MAGIC   requests

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json
import re
import tempfile
import warnings
from datetime import datetime, timezone

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

from phantom_census.existence_engine.data_loading import (
    build_district_to_state,
    load_districts,
    load_hfr,
)
from phantom_census.existence_engine.pipeline import EngineInputs, run_engine
from phantom_census.existence_engine.spatial import assign_districts

# COMMAND ----------
# ── 1. Read bronze UC tables ──────────────────────────────────────────────────

VF_CATALOG = "databricks_virtue_foundation_dataset_dais_2026"
VF_SCHEMA = "virtue_foundation_dataset"

facilities_raw = spark.table(f"{VF_CATALOG}.{VF_SCHEMA}.facilities").toPandas()
india_post_raw = spark.table(f"{VF_CATALOG}.{VF_SCHEMA}.india_post_pincode_directory").toPandas()
nfhs_raw = spark.table(f"{VF_CATALOG}.{VF_SCHEMA}.nfhs_5_district_health_indicators").toPandas()

print(f"facilities: {len(facilities_raw):,} rows")
print(f"india_post: {len(india_post_raw):,} rows")
print(f"nfhs:       {len(nfhs_raw):,} rows")

# COMMAND ----------
# ── 2. Normalise column names to match engine contracts ───────────────────────

facilities = facilities_raw.rename(columns={
    "unique_id": "facility_id",
    "name": "facility_name",
    "address_zipOrPostcode": "pincode",
})

india_post = india_post_raw.rename(columns={"statename": "state"})
india_post["pincode"] = india_post["pincode"].astype(str).str.strip()
india_post["latitude"] = pd.to_numeric(india_post["latitude"], errors="coerce")
india_post["longitude"] = pd.to_numeric(india_post["longitude"], errors="coerce")

nfhs = nfhs_raw.rename(columns={
    "district_name": "district",
    "state_ut": "state",
    "institutional_birth_5y_pct": "institutional_delivery_rate",
})
nfhs["institutional_delivery_rate"] = pd.to_numeric(
    nfhs["institutional_delivery_rate"].astype(str).str.replace("*", "", regex=False),
    errors="coerce",
)

print("Column normalisation complete")

# COMMAND ----------
# ── 3. Download geoBoundaries India ADM2 polygons (preserve shapeID) ──────────

GEO_URL = (
    "https://github.com/wmgeolab/geoBoundaries/raw/main/"
    "releaseData/gbOpen/IND/ADM2/geoBoundaries-IND-ADM2.geojson"
)

with tempfile.NamedTemporaryFile(suffix=".geojson", delete=False) as f:
    geo_path = f.name
    resp = requests.get(GEO_URL, timeout=120)
    resp.raise_for_status()
    f.write(resp.content)

districts = load_districts(geo_path)
print(f"Districts loaded: {len(districts)} polygons; has shapeID: {'shapeID' in districts.columns}")

# COMMAND ----------
# ── 4. Run the existence engine (6 tests + Layer B + Adjudicator + Layer A + Layer C) ──

ran_at = datetime.now(tz=timezone.utc)
snapshot_id = ran_at.strftime("%Y-%m-%d-batch-001")

inputs = EngineInputs(
    facilities=facilities,
    india_post=india_post,
    nfhs=nfhs,
    districts=districts,
    hfr=load_hfr(None),       # no HFR snapshot for demo
    district_to_state=None,    # engine will build from india_post + nfhs
    current_year=ran_at.year,
    snapshot_id=snapshot_id,
)

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    outputs = run_engine(inputs, ran_at=ran_at)

print(f"facility_existence_tests: {len(outputs.facility_existence_tests):,} rows")
print(f"phantom_verdicts:         {len(outputs.phantom_verdicts):,} rows")
print(f"description_embeddings:   {len(outputs.description_embeddings):,} rows")
print(f"facility_capabilities:    {len(outputs.facility_capabilities):,} rows")

verdict_counts = outputs.phantom_verdicts["verdict"].value_counts()
print(f"\nverdict mix:")
for k, v in verdict_counts.items():
    print(f"  {k}: {v:,}")

# COMMAND ----------
# ── 5. Build facility metadata sidecar (district + state lookup) ──────────────

facilities_with_district = assign_districts(facilities, districts)
district_to_state = build_district_to_state(india_post, nfhs)

facility_meta = facilities[["facility_id", "facility_name"]].copy()
facility_meta["district_id"] = facilities_with_district["district_id"].fillna("UNKNOWN")
facility_meta["district_name"] = facilities_with_district["spatial_district"].fillna("Unknown")
facility_meta["state_name"] = (
    facilities_with_district["spatial_district"]
    .map(district_to_state)
    .fillna(facilities.get("address_stateOrRegion", pd.Series(dtype=str)))
    .fillna("Unknown")
)

# COMMAND ----------
# ── 6. phantom_verdicts gold (dual-verdict columns + AI cache cols nulled) ────

verdicts_gold = outputs.phantom_verdicts.merge(facility_meta, on="facility_id", how="left")
verdicts_gold["test_outcome_vector"] = verdicts_gold["test_outcome_vector"].apply(
    lambda v: json.dumps(v) if v is not None else "[]"
)
verdicts_gold["rescue_applied"] = verdicts_gold["rescue_applied"].apply(
    lambda v: json.dumps(v) if v is not None else None
)
verdicts_gold["layer_c_synthesis"] = verdicts_gold["layer_c_synthesis"].apply(
    lambda v: json.dumps(v) if v is not None else None
)
verdicts_gold["ai_recommendation"] = None
verdicts_gold["ai_recommendation_evidence_state"] = None
verdicts_gold["override_id"] = None

verdicts_gold = verdicts_gold[[
    "facility_id", "adjudicator_verdict", "verdict", "reason",
    "rescue_applied", "test_outcome_vector", "layer_c_synthesis",
    "ai_recommendation", "ai_recommendation_evidence_state",
    "override_id", "ran_at",
]].drop_duplicates(subset=["facility_id"])

print(f"phantom_verdicts: {len(verdicts_gold):,} rows")

# COMMAND ----------
# ── 7. facility_existence_tests gold ──────────────────────────────────────────

tests_gold = outputs.facility_existence_tests.copy()
tests_gold["evidence_ref"] = tests_gold["evidence_ref"].apply(
    lambda v: json.dumps(v) if isinstance(v, (dict, list)) else
              ("null" if v is None else json.dumps(str(v)))
)
tests_gold = tests_gold[["facility_id", "test_name", "result", "evidence_ref", "ran_at"]]
print(f"facility_existence_tests: {len(tests_gold):,} rows")

# COMMAND ----------
# ── 8. description_embeddings gold (one row per (facility_id, snapshot_id)) ───

embeddings_gold = pd.DataFrame([
    {"facility_id": fid, "snapshot_id": snapshot_id,
     "embedding": blob, "computed_at": ran_at}
    for fid, blob in outputs.description_embeddings.items()
])
print(f"description_embeddings: {len(embeddings_gold):,} rows")

# COMMAND ----------
# ── 9. facility_capabilities gold (one row per (facility_id, capability)) ─────

capability_rows = []
for fid, caps in outputs.facility_capabilities.items():
    for cap in caps or []:
        capability_rows.append({"facility_id": fid, "capability": cap})
capabilities_gold = pd.DataFrame(capability_rows, columns=["facility_id", "capability"])
print(f"facility_capabilities: {len(capabilities_gold):,} rows")

# COMMAND ----------
# ── 10. desert_scores gold (per-capability) ───────────────────────────────────

CAPABILITIES = sorted({c for caps in outputs.facility_capabilities.values() for c in caps})
print(f"capabilities present: {CAPABILITIES}")

# Build per-facility verdict + meta + capability for grouping
fac_v = verdicts_gold[["facility_id", "verdict"]].merge(
    facility_meta, on="facility_id", how="left"
)

score_rows: list[dict] = []
for cap in CAPABILITIES:
    fac_ids_for_cap = capabilities_gold.loc[
        capabilities_gold["capability"] == cap, "facility_id"
    ]
    cap_df = fac_v[fac_v["facility_id"].isin(fac_ids_for_cap)].copy()
    if cap_df.empty:
        continue

    agg = cap_df.groupby(["district_id", "district_name", "state_name"]).agg(
        phantom_count=("verdict", lambda x: (x == "phantom").sum()),
        real_count=("verdict", lambda x: (x == "real").sum()),
        contested_count=("verdict", lambda x: (x == "contested").sum()),
    ).reset_index()
    agg["verified_facility_count"] = agg["real_count"] + agg["contested_count"]

    # Per-state normalization. Higher → more underserved.
    by_state = agg.groupby("state_name")
    max_count = by_state["verified_facility_count"].transform("max").clip(lower=1)
    agg["max_density"] = max_count.astype(float)
    agg["burden_weight"] = 0.5   # placeholder — gets refined when NFHS join is wired
    agg["raw_desert_score"] = (
        1.0 - (agg["verified_facility_count"] + agg["phantom_count"]) / max_count
    ).clip(0, 1)
    agg["adjusted_desert_score"] = (
        1.0 - agg["verified_facility_count"] / max_count
    ).clip(0, 1)
    agg["capability"] = cap
    agg["burden_imputed"] = False
    agg["nfhs_missing"] = False
    agg["updated_at"] = ran_at

    score_rows.append(agg[[
        "district_id", "district_name", "state_name", "capability",
        "raw_desert_score", "adjusted_desert_score",
        "verified_facility_count", "phantom_count",
        "burden_imputed", "nfhs_missing", "burden_weight", "max_density",
        "updated_at",
    ]])

desert_scores_gold = pd.concat(score_rows, ignore_index=True) if score_rows else pd.DataFrame()
print(f"desert_scores: {len(desert_scores_gold):,} rows across {len(CAPABILITIES)} capabilities")

# COMMAND ----------
# ── 11. budget_allocations gold (hand-curated Q3 demo allocation) ────────────

# Demo-time hand-curated allocation. Per LP-SCHEMA-BUDGET-002 this table is
# read-only from the app's perspective; the recommendation is exported to CSV.
# We seed one row per (district_id, capability='maternity', quarter='2026-Q3')
# based on prior-quarter facility count.

QUARTER = "2026-Q3"
PER_FACILITY_INR = 5_000_000   # ₹50 Lakh per verified facility, demo proxy

if not desert_scores_gold.empty:
    budget_seed = desert_scores_gold[desert_scores_gold["capability"] == "maternity"]
    if budget_seed.empty:
        budget_seed = desert_scores_gold[
            desert_scores_gold["capability"] == desert_scores_gold["capability"].iloc[0]
        ]
    budget_allocations_gold = pd.DataFrame({
        "district_id":   budget_seed["district_id"].values,
        "state_name":    budget_seed["state_name"].values,
        "capability":    "maternity",
        "quarter":       QUARTER,
        "allocated_inr": (
            budget_seed["verified_facility_count"].fillna(0).astype(int)
            * PER_FACILITY_INR
        ).values,
        "loaded_at":     ran_at,
    })
else:
    budget_allocations_gold = pd.DataFrame(columns=[
        "district_id", "state_name", "capability", "quarter",
        "allocated_inr", "loaded_at",
    ])

print(f"budget_allocations: {len(budget_allocations_gold):,} rows")

# COMMAND ----------
# ── 12. facilities slim sidecar (for map scatter + audit queue) ──────────────

facilities_slim = facilities[[
    "facility_id", "facility_name", "address_city", "address_stateOrRegion",
    "latitude", "longitude", "pincode", "capability", "description", "yearEstablished",
]].drop_duplicates(subset=["facility_id"]).copy()
print(f"facilities: {len(facilities_slim):,} rows")

# COMMAND ----------
# ── 13. Write gold Delta tables to Unity Catalog ──────────────────────────────

GOLD_CATALOG = "workspace"
GOLD_SCHEMA = "phantom_census"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {GOLD_CATALOG}.{GOLD_SCHEMA}")


def write_gold(df: pd.DataFrame, table: str) -> None:
    fqn = f"{GOLD_CATALOG}.{GOLD_SCHEMA}.{table}"
    if df.empty:
        print(f"  ✗ {fqn}: empty — skipped")
        return
    # Convert via Arrow to avoid Spark-Pandas dtype edge cases on JSONB/bytes.
    sdf = spark.createDataFrame(df)
    sdf.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(fqn)
    print(f"  ✓ {fqn}: {sdf.count():,} rows")


print("Writing gold tables...")
write_gold(facilities_slim,           "facilities")
write_gold(verdicts_gold,             "phantom_verdicts")
write_gold(tests_gold,                "facility_existence_tests")
write_gold(desert_scores_gold,        "desert_scores")
write_gold(embeddings_gold,           "description_embeddings")
write_gold(capabilities_gold,         "facility_capabilities")
write_gold(budget_allocations_gold,   "budget_allocations")

print("\nAll gold tables written. Next: docs/setup-synced-tables.sh creates "
      "synced tables in Lakebase + grants the app SP SELECT.")

# COMMAND ----------
# ── 14. Enable CDF for future TRIGGERED-mode sync ─────────────────────────────

for table in (
    "facilities", "phantom_verdicts", "facility_existence_tests",
    "desert_scores", "description_embeddings", "facility_capabilities",
    "budget_allocations",
):
    fqn = f"{GOLD_CATALOG}.{GOLD_SCHEMA}.{table}"
    spark.sql(
        f"ALTER TABLE {fqn} "
        f"SET TBLPROPERTIES (delta.enableChangeDataFeed = true)"
    )
    print(f"  CDF enabled: {fqn}")
