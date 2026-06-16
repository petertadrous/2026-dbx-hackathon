#!/usr/bin/env bash
# Lakebase synced-tables setup — non-interactive, idempotent.
#
# Per LP-SYNC-001..LP-SYNC-006:
#   1. Register the phantom_census_lakebase UC catalog against the Lakebase project
#   2. Create one synced table per gold table in workspace.phantom_census.*
#   3. Wait for each synced table to reach ONLINE state
#   4. Grant the app service principal SELECT on the public schema
#
# Prerequisites:
#   - notebooks/existence_engine.py has run and written workspace.phantom_census.*
#   - The Lakebase project `phantom-census` exists with the `production` branch
#   - The Databricks App `phantom-census` is deployed (the SP exists)

set -euo pipefail

PROFILE="${DATABRICKS_PROFILE:-DEFAULT}"
PROJECT="phantom-census"
BRANCH="projects/${PROJECT}/branches/production"
DB="databricks_postgres"
LAKEBASE_CATALOG="phantom_census_lakebase"
STORAGE_CATALOG="workspace"
STORAGE_SCHEMA="default"
GOLD_CATALOG="workspace"
GOLD_SCHEMA="phantom_census"
APP_NAME="phantom-census"
ENDPOINT="${BRANCH}/endpoints/primary"

log() { echo "[setup-synced-tables] $*"; }

# ─── Step 1: register the Lakebase-backed UC catalog ──────────────────────────

log "Step 1/4: registering ${LAKEBASE_CATALOG} catalog…"
if databricks postgres list-catalogs "${BRANCH}" --profile "${PROFILE}" -o json 2>/dev/null \
    | python3 -c "import json,sys; cs=json.load(sys.stdin); sys.exit(0 if any(c.get('uc_catalog_name')=='${LAKEBASE_CATALOG}' or c.get('name','').endswith('/${LAKEBASE_CATALOG}') for c in cs) else 1)" \
    2>/dev/null; then
  log "  ${LAKEBASE_CATALOG} already registered — skipping"
else
  databricks postgres create-catalog "${LAKEBASE_CATALOG}" \
    --json "{
      \"spec\": {
        \"postgres_database\": \"${DB}\",
        \"branch\": \"${BRANCH}\"
      }
    }" \
    --profile "${PROFILE}" -o json > /dev/null
  log "  ${LAKEBASE_CATALOG} registered"
fi

# ─── Step 2: create synced tables per LP-SYNC-001 ─────────────────────────────

# Format: <table>|<comma-sep PKs>
# Per LP-SYNC-003 — primary keys mirror the operational/cache/team schema PKs.
SYNCED_TABLES=(
  "facilities|facility_id"
  "phantom_verdicts|facility_id"
  "facility_existence_tests|facility_id,test_name,ran_at"
  "desert_scores|district_id,capability"
  "description_embeddings|facility_id,snapshot_id"
  "facility_capabilities|facility_id,capability"
  "budget_allocations|district_id,capability,quarter"
)

log "Step 2/4: creating synced tables…"
CREATED_NAMES=()
for entry in "${SYNCED_TABLES[@]}"; do
  TABLE="${entry%%|*}"
  PKS="${entry##*|}"

  IFS=',' read -ra PK_ARR <<< "${PKS}"
  PK_JSON=$(printf '"%s",' "${PK_ARR[@]}")
  PK_JSON="[${PK_JSON%,}]"

  SYNCED="${LAKEBASE_CATALOG}.public.${TABLE}"
  SRC="${GOLD_CATALOG}.${GOLD_SCHEMA}.${TABLE}"
  CREATED_NAMES+=("${SYNCED}")

  if databricks postgres get-synced-table "synced_tables/${SYNCED}" --profile "${PROFILE}" \
      -o json > /dev/null 2>&1; then
    log "  ${SYNCED} already exists — skipping create"
    continue
  fi

  log "  ${SRC} → ${SYNCED} (PK: ${PKS})"
  databricks postgres create-synced-table \
    "${SYNCED}" \
    --json "{
      \"spec\": {
        \"source_table_full_name\": \"${SRC}\",
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
    --profile "${PROFILE}" --no-wait -o json > /dev/null
done

# ─── Step 3: poll until every synced table reaches ONLINE ─────────────────────

log "Step 3/4: waiting for synced tables to reach ONLINE state…"
DEADLINE=$(( $(date +%s) + 1800 ))   # 30 min cap
while :; do
  remaining=0
  for name in "${CREATED_NAMES[@]}"; do
    state=$(databricks postgres get-synced-table "synced_tables/${name}" --profile "${PROFILE}" -o json 2>/dev/null \
            | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status',{}).get('detailed_state','UNKNOWN'))" 2>/dev/null || echo "UNKNOWN")
    case "${state}" in
      ONLINE|ONLINE_TRIGGERED_UPDATE_SUCCEEDED|ONLINE_NO_PENDING_UPDATE) ;;
      *) remaining=$((remaining + 1)); log "  ${name}: ${state}";;
    esac
  done
  if [[ "${remaining}" -eq 0 ]]; then
    log "  all synced tables ONLINE"
    break
  fi
  if [[ "$(date +%s)" -gt "${DEADLINE}" ]]; then
    log "  TIMEOUT — ${remaining} table(s) still not ONLINE after 30min. Re-run later."
    exit 1
  fi
  sleep 20
done

# ─── Step 4: grant the app SP SELECT on public ────────────────────────────────

log "Step 4/4: granting app SP SELECT on public schema…"
SP_ID=$(databricks apps get "${APP_NAME}" --profile "${PROFILE}" -o json \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['service_principal_client_id'])")
log "  app SP client id: ${SP_ID}"

HOST=$(databricks postgres get-endpoint "${ENDPOINT}" --profile "${PROFILE}" -o json \
       | python3 -c "import json,sys; print(json.load(sys.stdin)['status']['hosts']['host'])")
TOKEN=$(databricks postgres generate-database-credential "${ENDPOINT}" --profile "${PROFILE}" -o json \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['token'])")
USER=$(databricks current-user me --profile "${PROFILE}" -o json \
       | python3 -c "import json,sys; print(json.load(sys.stdin)['userName'])")

if ! command -v psql > /dev/null; then
  log "  WARNING: psql not on PATH. Run these GRANTs manually:"
  echo "    GRANT USAGE ON SCHEMA public TO \"${SP_ID}\";"
  echo "    GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"${SP_ID}\";"
  echo "    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO \"${SP_ID}\";"
  exit 0
fi

PGPASSWORD="${TOKEN}" psql \
  "host=${HOST} user=${USER} dbname=${DB} sslmode=require" \
  -v ON_ERROR_STOP=1 \
  -c "GRANT USAGE ON SCHEMA public TO \"${SP_ID}\";" \
  -c "GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"${SP_ID}\";" \
  -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO \"${SP_ID}\";"

log "Done. The Streamlit app should now see synced data on next restart."
