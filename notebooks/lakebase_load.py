# Databricks notebook source
# Reads gold Delta tables from UC → writes directly to Lakebase Postgres.
# Run standalone after existence_engine, or use the phantom-census-pipeline job
# which chains both notebooks so only this task needs to be repaired on write failures.

# COMMAND ----------

# MAGIC %pip install --quiet "databricks-sdk>=0.81.0"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import pandas as pd
from databricks.sdk import WorkspaceClient
import psycopg2
import psycopg2.extras

GOLD_CATALOG  = "workspace"
GOLD_SCHEMA   = "phantom_census"
LAKEBASE_EP   = "projects/phantom-census/branches/production/endpoints/primary"
LAKEBASE_HOST = "ep-empty-rice-d8xtqsho.database.us-east-2.cloud.databricks.com"

# COMMAND ----------
# ── 1. Read gold Delta tables from UC ────────────────────────────────────────

print("Reading from UC gold tables...")
verdicts        = spark.table(f"{GOLD_CATALOG}.{GOLD_SCHEMA}.phantom_verdicts").toPandas()
tests           = spark.table(f"{GOLD_CATALOG}.{GOLD_SCHEMA}.facility_existence_tests").toPandas()
desert_scores   = spark.table(f"{GOLD_CATALOG}.{GOLD_SCHEMA}.desert_scores").toPandas()
tiles_df        = spark.table(f"{GOLD_CATALOG}.{GOLD_SCHEMA}.tile_layers").toPandas()
facilities_slim = spark.table(f"{GOLD_CATALOG}.{GOLD_SCHEMA}.facilities").toPandas()

print(f"  phantom_verdicts:         {len(verdicts):,} rows")
print(f"  facility_existence_tests: {len(tests):,} rows")
print(f"  desert_scores:            {len(desert_scores):,} rows")
print(f"  tile_layers:              {len(tiles_df):,} rows")
print(f"  facilities:               {len(facilities_slim):,} rows")

# COMMAND ----------
# ── 2. Connect to Lakebase ───────────────────────────────────────────────────

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
    raw_rank                INT,
    adjusted_rank           INT,
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

-- Add rank columns to existing tables (idempotent for re-runs)
ALTER TABLE public.desert_scores ADD COLUMN IF NOT EXISTS raw_rank INT;
ALTER TABLE public.desert_scores ADD COLUMN IF NOT EXISTS adjusted_rank INT;

-- Indexes for app query performance
CREATE INDEX IF NOT EXISTS idx_desert_scores_cap
    ON public.desert_scores(capability, adjusted_desert_score DESC);
CREATE INDEX IF NOT EXISTS idx_verdicts_district
    ON public.phantom_verdicts(district_id);
CREATE INDEX IF NOT EXISTS idx_tests_facility
    ON public.facility_existence_tests(facility_id);
""")
print("DDL applied.")

# COMMAND ----------
# ── 3. Write to Lakebase ─────────────────────────────────────────────────────

def _strip_null_bytes(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].apply(lambda v: v.replace("\x00", "") if isinstance(v, str) else v)
    return df


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


# Precompute per-capability district ranks so the app can use a simple SELECT
# instead of RANK() OVER window functions at query time.
desert_scores["raw_rank"] = (
    desert_scores.groupby("capability")["raw_desert_score"]
    .rank(ascending=False, method="min").astype(int)
)
desert_scores["adjusted_rank"] = (
    desert_scores.groupby("capability")["adjusted_desert_score"]
    .rank(ascending=False, method="min").astype(int)
)

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
    print("  Run manually: GRANT USAGE ON SCHEMA public TO \"<SP_CLIENT_ID>\";")
    print("                GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"<SP_CLIENT_ID>\";")

conn.close()
print("\nLakebase write complete — app is ready.")
