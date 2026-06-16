# Databricks notebook source
# Run on DBR 14.3 ML (includes geopandas system libs).
# Reads bronze UC tables → runs the 5-signal existence engine → writes gold Delta tables.
# Gold tables are then synced to Lakebase via `databricks postgres create-synced-table`.

# COMMAND ----------

# MAGIC %pip install --quiet \
# MAGIC   "git+https://github.com/petertadrous/2026-dbx-hackathon.git" \
# MAGIC   "databricks-sdk>=0.81.0" \
# MAGIC   folium==0.18.0 \
# MAGIC   requests

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json
import math
import re
import tempfile
import warnings
from datetime import datetime, timezone

import folium
import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from pyspark.sql import functions as F

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

# facilities: unique_id → facility_id, name → facility_name, address_zipOrPostcode → pincode
# unique_id is not guaranteed unique in the VF dataset — deduplicate before
# the engine so every signal test emits exactly one row per facility_id.
facilities = (
    facilities_raw
    .rename(columns={
        "unique_id": "facility_id",
        "name": "facility_name",
        "address_zipOrPostcode": "pincode",
    })
    .drop_duplicates(subset=["facility_id"])
    .reset_index(drop=True)
)

# india_post: statename → state (load_india_post handles this but we're bypassing
# the file loader here, so do it manually); cast lat/lon to float
india_post = india_post_raw.rename(columns={"statename": "state"})
india_post["pincode"] = india_post["pincode"].astype(str).str.strip()
india_post["latitude"] = pd.to_numeric(india_post["latitude"], errors="coerce")
india_post["longitude"] = pd.to_numeric(india_post["longitude"], errors="coerce")

# nfhs: district_name → district, state_ut → state,
# institutional_birth_5y_pct → institutional_delivery_rate
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
# ── 3. Download geoBoundaries India ADM2 district polygons ────────────────────

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
print(f"Districts loaded: {len(districts)} polygons")

# COMMAND ----------
# ── 4. Run the existence engine ───────────────────────────────────────────────

ran_at = datetime.now(tz=timezone.utc)

inputs = EngineInputs(
    facilities=facilities,
    india_post=india_post,
    nfhs=nfhs,
    districts=districts,
    hfr=load_hfr(None),       # no HFR snapshot for demo
    district_to_state=None,    # engine will build from india_post + nfhs
    current_year=ran_at.year,
)

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    outputs = run_engine(inputs, ran_at=ran_at)

print(f"facility_existence_tests: {len(outputs.facility_existence_tests):,} rows")
print(f"phantom_verdicts:         {len(outputs.phantom_verdicts):,} rows")

verdict_counts = outputs.phantom_verdicts["verdict"].value_counts()
print(f"  phantom:   {verdict_counts.get('phantom', 0):,}")
print(f"  contested: {verdict_counts.get('contested', 0):,}")
print(f"  real:      {verdict_counts.get('real', 0):,}")

# COMMAND ----------
# ── 5. Enrich phantom_verdicts with facility metadata and district info ────────

facilities_with_district = assign_districts(facilities, districts)
district_to_state = build_district_to_state(india_post, nfhs)

# Build facility metadata sidecar
facility_meta = facilities[["facility_id", "facility_name"]].copy()
facility_meta["district_id"] = (
    facilities_with_district["spatial_district"]
    .str.lower()
    .str.replace(r"[^a-z0-9]", "", regex=True)
)
facility_meta["district_name"] = facilities_with_district["spatial_district"]
facility_meta["state_name"] = (
    facilities_with_district["spatial_district"]
    .map(district_to_state)
    .fillna(facilities.get("address_stateOrRegion", pd.Series(dtype=str)))
)

verdicts = outputs.phantom_verdicts.merge(facility_meta, on="facility_id", how="left")

# Serialise test_outcome_vector (list[dict]) → JSON string for Delta storage
verdicts["test_outcome_vector"] = verdicts["test_outcome_vector"].apply(
    lambda v: json.dumps(v) if v is not None else "[]"
)

verdicts = verdicts[
    ["facility_id", "facility_name", "district_id", "district_name",
     "state_name", "verdict", "reason", "test_outcome_vector", "ran_at"]
].drop_duplicates(subset=["facility_id"])

print(f"phantom_verdicts enriched: {len(verdicts):,} rows, "
      f"{verdicts['district_name'].nunique()} districts")

# COMMAND ----------
# ── 6. Enrich facility_existence_tests ────────────────────────────────────────

tests = outputs.facility_existence_tests.copy()
tests["evidence_ref"] = tests["evidence_ref"].apply(
    lambda v: json.dumps(v) if isinstance(v, (dict, list)) else
              ("null" if v is None else json.dumps(str(v)))
)
tests = (
    tests[["facility_id", "test_name", "result", "evidence_ref", "ran_at"]]
    .drop_duplicates(subset=["facility_id", "test_name"], keep="last")
)

# COMMAND ----------
# ── 7. Compute desert scores per district per capability ──────────────────────

CAPABILITIES = ["maternity", "icu", "emergency", "trauma", "nicu"]

CAPABILITY_KEYWORDS: dict[str, list[str]] = {
    "maternity": ["maternity", "delivery", "obstetric", "antenatal", "postnatal",
                  "labour", "labor", "cesarean", "caesarean", "gynaecol", "gynecol",
                  "neonatal", "prenatal"],
    "icu":       ["icu", "intensive care", "critical care", "ventilat", "icu bed"],
    "emergency": ["emergency", "casualty", "accident", "urgent care", "24.*hour"],
    "trauma":    ["trauma", "burns", "burn", "orthopedic", "orthopaedic",
                  "fracture", "surgery", "surgical", "operation theatre"],
    "nicu":      ["nicu", "neonatal", "newborn", "premature", "incubator"],
}


def _claims_text(row: pd.Series) -> str:
    parts = [
        row.get("capability") or "",
        row.get("procedure") or "",
        row.get("equipment") or "",
        row.get("description") or "",
    ]
    return " ".join(str(p) for p in parts if p and str(p) != "nan").lower()


facilities_claims = facilities.copy()
facilities_claims["_claims_text"] = facilities_claims.apply(_claims_text, axis=1)

for cap, keywords in CAPABILITY_KEYWORDS.items():
    pat = "|".join(re.escape(k) for k in keywords)
    facilities_claims[f"claims_{cap}"] = facilities_claims["_claims_text"].str.contains(
        pat, case=False, regex=True, na=False
    )

# Merge facility metadata into verdicts for scoring
verdicts_meta = verdicts.merge(
    facilities_claims[["facility_id"] + [f"claims_{c}" for c in CAPABILITIES]],
    on="facility_id",
    how="left",
)

score_rows: list[dict] = []

for cap in CAPABILITIES:
    cap_df = verdicts_meta[verdicts_meta[f"claims_{cap}"].fillna(False)].copy()

    # Group only on district_id — district_name/state_name vary in casing
    # across facilities for the same district, which would produce duplicate
    # (district_id, capability) rows and violate the Lakebase PK.
    district_agg = cap_df.groupby("district_id", as_index=False).agg(
        district_name=("district_name", "first"),
        state_name=("state_name", "first"),
        phantom_count=("verdict", lambda x: (x == "phantom").sum()),
        real_count=("verdict", lambda x: (x == "real").sum()),
        contested_count=("verdict", lambda x: (x == "contested").sum()),
    )

    district_agg["total_count"] = (
        district_agg["phantom_count"]
        + district_agg["real_count"]
        + district_agg["contested_count"]
    )
    district_agg["verified_facility_count"] = (
        district_agg["real_count"] + district_agg["contested_count"]
    )

    # Desert score = inverse facility density, normalised within state.
    # Higher score → more underserved (fewer verified facilities relative to peers).
    by_state = district_agg.groupby("state_name")
    district_agg["_max_raw"] = by_state["total_count"].transform("max").clip(lower=1)
    district_agg["_max_verified"] = by_state["verified_facility_count"].transform("max").clip(lower=1)

    district_agg["raw_desert_score"] = (
        1.0 - district_agg["total_count"] / district_agg["_max_raw"]
    ).clip(0, 1)
    district_agg["adjusted_desert_score"] = (
        1.0 - district_agg["verified_facility_count"] / district_agg["_max_verified"]
    ).clip(0, 1)

    district_agg["capability"] = cap
    district_agg["burden_imputed"] = False
    district_agg["updated_at"] = ran_at

    score_rows.append(district_agg[[
        "district_id", "district_name", "state_name", "capability",
        "raw_desert_score", "adjusted_desert_score",
        "verified_facility_count", "phantom_count", "contested_count",
        "total_count", "burden_imputed", "updated_at",
    ]])

desert_scores = pd.concat(score_rows, ignore_index=True)
print(f"desert_scores: {len(desert_scores):,} rows across {len(CAPABILITIES)} capabilities")

# Top 5 rank shifts for maternity
mat = desert_scores[desert_scores["capability"] == "maternity"].copy()
mat["raw_rank"] = mat["raw_desert_score"].rank(ascending=False, method="min").astype(int)
mat["adj_rank"] = mat["adjusted_desert_score"].rank(ascending=False, method="min").astype(int)
mat["rank_shift"] = mat["adj_rank"] - mat["raw_rank"]
top_shifts = mat.nlargest(5, "rank_shift")[["district_name", "state_name", "raw_rank", "adj_rank", "rank_shift"]]
print("\nTop 5 district rank shifts (maternity, adjusted − raw):")
print(top_shifts.to_string(index=False))

# COMMAND ----------
# ── 8. Generate Folium choropleth HTML tiles ──────────────────────────────────

def build_choropleth(
    districts_gdf: gpd.GeoDataFrame,
    scores_df: pd.DataFrame,
    score_col: str,
    title: str,
    colormap: str = "RdYlGn_r",
) -> str:
    merged = districts_gdf.merge(
        scores_df[["district_name", score_col]],
        left_on="district",
        right_on="district_name",
        how="left",
    )
    merged[score_col] = merged[score_col].fillna(0.5)

    m = folium.Map(location=[22.0, 79.0], zoom_start=5, tiles="CartoDB positron")

    folium.Choropleth(
        geo_data=merged.__geo_interface__,
        data=merged[["district", score_col]],
        columns=["district", score_col],
        key_on="feature.properties.district",
        fill_color=colormap,
        fill_opacity=0.65,
        line_opacity=0.2,
        legend_name=title,
        nan_fill_color="#d0d0d0",
    ).add_to(m)

    folium.LayerControl().add_to(m)
    return m._repr_html_()


tile_rows: list[dict] = []

for cap in CAPABILITIES:
    cap_scores = desert_scores[desert_scores["capability"] == cap]

    for layer_type, score_col, label in [
        ("raw",      "raw_desert_score",      f"{cap.title()} desert — raw"),
        ("adjusted", "adjusted_desert_score",  f"{cap.title()} desert — phantom-adjusted"),
    ]:
        try:
            html = build_choropleth(districts, cap_scores, score_col, label)
            tile_rows.append({
                "capability": cap,
                "layer_type": layer_type,
                "html": html,
                "rendered_at": ran_at,
            })
            print(f"  tile {cap}/{layer_type}: {len(html):,} chars")
        except Exception as exc:
            print(f"  WARN: tile {cap}/{layer_type} failed — {exc}")

tiles_df = pd.DataFrame(tile_rows)
print(f"\ntile_layers: {len(tiles_df)} tiles generated")

# COMMAND ----------
# ── 9. Write gold Delta tables to Unity Catalog ───────────────────────────────

GOLD_CATALOG = "workspace"
GOLD_SCHEMA = "phantom_census"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {GOLD_CATALOG}.{GOLD_SCHEMA}")


def _strip_null_bytes(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.select_dtypes(include=["object", "str"]).columns:
        df[col] = df[col].apply(lambda v: v.replace("\x00", "") if isinstance(v, str) else v)
    return df


def write_gold(df: pd.DataFrame, table: str) -> None:
    fqn = f"{GOLD_CATALOG}.{GOLD_SCHEMA}.{table}"
    import pyarrow as pa
    df = _strip_null_bytes(df.copy())
    arrow_table = pa.Table.from_pandas(df).combine_chunks()
    sdf = spark.createDataFrame(arrow_table.to_pandas())
    sdf.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(fqn)
    print(f"  ✓ {fqn}: {sdf.count():,} rows")


print("Writing gold tables...")
write_gold(verdicts,      "phantom_verdicts")
write_gold(tests,         "facility_existence_tests")
write_gold(desert_scores, "desert_scores")
write_gold(tiles_df,      "tile_layers")

# Also write the facilities table for lookup by the app.
# unique_id is not guaranteed unique in the VF dataset — deduplicate before writing.
facilities_slim = facilities[[
    "facility_id", "facility_name", "address_city", "address_stateOrRegion",
    "latitude", "longitude", "pincode", "capability", "description", "yearEstablished",
]].drop_duplicates(subset=["facility_id"]).copy()
write_gold(facilities_slim, "facilities")

print("\nAll gold tables written.")

# COMMAND ----------
# ── 10. Write directly to Lakebase Postgres ───────────────────────────────────
# Synced tables require DLT compute, unavailable on Free Edition.
# At ~10K rows the direct psycopg2 path is trivially fast.

from databricks.sdk import WorkspaceClient
import psycopg2
import psycopg2.extras

LAKEBASE_EP   = "projects/phantom-census/branches/production/endpoints/primary"
LAKEBASE_HOST = "ep-empty-rice-d8xtqsho.database.us-east-2.cloud.databricks.com"

w    = WorkspaceClient()
cred = w.postgres.generate_database_credential(LAKEBASE_EP)
me   = w.current_user.me()

conn = psycopg2.connect(
    host=LAKEBASE_HOST,
    user=me.user_name,
    password=cred.token,
    dbname="databricks_postgres",
    sslmode="require",
)
conn.autocommit = True
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS public.phantom_verdicts (
    facility_id           TEXT PRIMARY KEY,
    facility_name         TEXT,
    district_id           TEXT,
    district_name         TEXT,
    state_name            TEXT,
    verdict               TEXT,
    reason                TEXT,
    test_outcome_vector   TEXT,
    ran_at                TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS public.facility_existence_tests (
    facility_id  TEXT,
    test_name    TEXT,
    result       TEXT,
    evidence_ref TEXT,
    ran_at       TIMESTAMPTZ,
    PRIMARY KEY (facility_id, test_name)
);

CREATE TABLE IF NOT EXISTS public.desert_scores (
    district_id             TEXT,
    capability              TEXT,
    district_name           TEXT,
    state_name              TEXT,
    raw_desert_score        DOUBLE PRECISION,
    adjusted_desert_score   DOUBLE PRECISION,
    verified_facility_count INT,
    phantom_count           INT,
    contested_count         INT,
    total_count             INT,
    burden_imputed          BOOLEAN,
    updated_at              TIMESTAMPTZ,
    PRIMARY KEY (district_id, capability)
);

CREATE TABLE IF NOT EXISTS public.tile_layers (
    capability  TEXT,
    layer_type  TEXT,
    html        TEXT,
    rendered_at TIMESTAMPTZ,
    PRIMARY KEY (capability, layer_type)
);

CREATE TABLE IF NOT EXISTS public.facilities (
    facility_id              TEXT PRIMARY KEY,
    facility_name            TEXT,
    address_city             TEXT,
    "address_stateOrRegion"  TEXT,
    latitude                 DOUBLE PRECISION,
    longitude                DOUBLE PRECISION,
    pincode                  TEXT,
    capability               TEXT,
    description              TEXT,
    "yearEstablished"        TEXT
);
""")
print("DDL applied.")


def _write_table(df: pd.DataFrame, table: str, on_conflict: str = "") -> None:
    clean = _strip_null_bytes(df.copy()).where(pd.notnull(df), other=None)
    cols  = list(clean.columns)
    col_list = ", ".join(f'"{c}"' for c in cols)
    cur.execute(f'TRUNCATE TABLE public."{table}"')
    psycopg2.extras.execute_values(
        cur,
        f'INSERT INTO public."{table}" ({col_list}) VALUES %s {on_conflict}'.strip(),
        [tuple(row) for row in clean.itertuples(index=False)],
        page_size=500,
    )
    print(f"  ✓ public.{table}: {len(clean):,} rows")


print("Writing to Lakebase...")
_write_table(verdicts,        "phantom_verdicts")
_write_table(tests,           "facility_existence_tests",
             "ON CONFLICT (facility_id, test_name) DO NOTHING")
_write_table(desert_scores,   "desert_scores")
_write_table(tiles_df,        "tile_layers")
_write_table(facilities_slim, "facilities")

# Grant app service principal read access to public schema.
try:
    app = w.apps.get("phantom-census-app")
    sp  = str(app.service_principal_client_id)
    cur.execute(f'GRANT USAGE ON SCHEMA public TO "{sp}"')
    cur.execute(f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "{sp}"')
    cur.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO "{sp}"')
    print(f"  ✓ Granted public schema read access to SP {sp}")
except Exception as exc:
    print(f"  WARN: auto-grant failed ({exc})")
    print("  Run manually in psql:")
    print("    GRANT USAGE ON SCHEMA public TO \"<SP_CLIENT_ID>\";")
    print("    GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"<SP_CLIENT_ID>\";")

conn.close()
print("\nLakebase write complete — app is ready.")
