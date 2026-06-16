#!/usr/bin/env bash
# Run this AFTER the Databricks notebook has completed and written gold tables to
# workspace.phantom_census.*.
#
# Order matters:
#   1. Register the phantom_census_lakebase UC catalog to the Lakebase project
#   2. Deploy the app (so the SP is created and can own the team.* schema)
#   3. Create synced tables (SNAPSHOT — one-time, re-run to refresh after notebook re-run)
#   4. Grant the app SP SELECT on the public schema

set -euo pipefail

PROFILE="DEFAULT"
PROJECT="phantom-census"
BRANCH="projects/${PROJECT}/branches/production"
DB="databricks_postgres"      # Postgres database name (not resource path)
LAKEBASE_CATALOG="phantom_census_lakebase"
STORAGE_CATALOG="workspace"   # regular UC catalog for DLT pipeline metadata
STORAGE_SCHEMA="default"
GOLD_CATALOG="workspace"
GOLD_SCHEMA="phantom_census"
APP_NAME="phantom-census-app"

echo "=== Step 1: Register phantom_census_lakebase catalog to the Lakebase project ==="
databricks postgres create-catalog "${LAKEBASE_CATALOG}" \
  --json "{
    \"spec\": {
      \"postgres_database\": \"${DB}\",
      \"branch\": \"${BRANCH}\"
    }
  }" \
  --profile "${PROFILE}" || echo "Catalog may already be registered — continuing"

echo ""
echo "=== Step 2: Deploy the app (creates the Service Principal) ==="
echo "Run from phantom-census-app/:"
echo "  cd phantom-census-app"
echo "  databricks bundle deploy --profile ${PROFILE}"
echo "  cd .."
echo ""
echo "Wait for the deploy to complete, then press ENTER to continue."
read -r

echo ""
echo "=== Step 3: Create synced tables (SNAPSHOT) ==="
# SNAPSHOT mode: one-time copy.  No CDF required.
# Re-run these commands after re-running the notebook to refresh data.

TABLES=(
  "facilities"
  "phantom_verdicts"
  "facility_existence_tests"
  "desert_scores"
  "tile_layers"
)

PRIMARY_KEYS=(
  "facility_id"
  "facility_id"
  "facility_id,test_name,ran_at"
  "district_id,capability"
  "capability,layer_type"
)

for i in "${!TABLES[@]}"; do
  TABLE="${TABLES[$i]}"
  PKS="${PRIMARY_KEYS[$i]}"

  # Build JSON array of primary key columns
  IFS=',' read -ra PK_ARR <<< "${PKS}"
  PK_JSON=$(printf '"%s",' "${PK_ARR[@]}")
  PK_JSON="[${PK_JSON%,}]"

  echo "Syncing ${GOLD_CATALOG}.${GOLD_SCHEMA}.${TABLE} → ${LAKEBASE_CATALOG}.public.${TABLE}"
  databricks postgres create-synced-table \
    "${LAKEBASE_CATALOG}.public.${TABLE}" \
    --json "{
      \"spec\": {
        \"source_table_full_name\": \"${GOLD_CATALOG}.${GOLD_SCHEMA}.${TABLE}\",
        \"primary_key_columns\": ${PK_JSON},
        \"scheduling_policy\": \"SNAPSHOT\",
        \"branch\": \"${BRANCH}\",
        \"postgres_database\": \"${DB}\",
        \"create_database_objects_if_missing\": true,
        \"new_pipeline_spec\": {
          \"storage_catalog\": \"${STORAGE_CATALOG}\",
          \"storage_schema\": \"${STORAGE_SCHEMA}\"
        }
      }
    }" \
    --profile "${PROFILE}" \
    --no-wait
  echo "  Triggered (async). Check status with:"
  echo "  databricks postgres get-synced-table \"synced_tables/${LAKEBASE_CATALOG}.public.${TABLE}\" --profile ${PROFILE}"
  echo ""
done

echo ""
echo "=== Step 4: Grant app SP SELECT on the public schema ==="
echo "Wait for all syncs to reach ONLINE state, then get the SP client ID:"
echo "  SP_ID=\$(databricks apps get ${APP_NAME} --profile ${PROFILE} --output json | python3 -c \"import json,sys; print(json.load(sys.stdin)['service_principal_client_id'])\")"
echo ""
echo "Then connect to Lakebase and run:"
echo "  GRANT USAGE ON SCHEMA public TO \"\$SP_ID\";"
echo "  GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"\$SP_ID\";"
echo "  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO \"\$SP_ID\";"
echo ""
echo "Connect via:"
echo "  EP=projects/${PROJECT}/branches/production/endpoints/primary"
echo "  HOST=\$(databricks postgres get-endpoint \$EP --profile ${PROFILE} -o json | python3 -c \"import json,sys; print(json.load(sys.stdin)['status']['hosts']['host'])\")"
echo "  TOKEN=\$(databricks postgres generate-database-credential \$EP --profile ${PROFILE} -o json | python3 -c \"import json,sys; print(json.load(sys.stdin)['token'])\")"
echo "  PGPASSWORD=\"\$TOKEN\" psql \"host=\$HOST user=kilotao dbname=databricks_postgres sslmode=require\""
