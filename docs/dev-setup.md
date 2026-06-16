# Developer Setup

## Running the test suite

```bash
uv sync --extra dev
uv run pytest tests
```

The existence-engine, desert-scoring, and planner-workspace test groups run
without external dependencies.

## Running the Lakebase integration tests

Lakebase tests use [`testcontainers`](https://testcontainers-python.readthedocs.io/)
to start an ephemeral Postgres container. Without a Docker daemon, those tests
skip cleanly per the `tests/lakebase/conftest.py:_can_use_docker` check.

### macOS via colima

The Python `docker` SDK and `testcontainers` both probe the default Unix
socket (`/var/run/docker.sock`). [Colima](https://github.com/abiosoft/colima)
publishes its socket under `~/.colima/default/docker.sock` instead, so two
env vars are needed:

```bash
colima start
export DOCKER_HOST=unix:///Users/peter/.colima/default/docker.sock
# Colima's vfs doesn't support mounting the docker socket into a sibling
# container, so disable testcontainers' Ryuk reaper:
export TESTCONTAINERS_RYUK_DISABLED=true
uv run pytest tests
```

Substitute your own user path in `DOCKER_HOST` if not `peter`.

### Linux with native Docker

Should work out of the box — no env vars needed. The `docker` SDK finds the
default socket, and Ryuk runs as the reaper container.

### Existing Postgres

To bypass testcontainers entirely (e.g. on CI with a managed Postgres):

```bash
export LAKEBASE_TEST_URL="postgresql+psycopg://user:pass@host:5432/db"
uv run pytest tests/lakebase
```

The conftest checks `LAKEBASE_TEST_URL` first and uses it as the engine
URL when set.

## Running the Streamlit app

```bash
uv sync --extra app
uv run streamlit run app.py
```

The app reads its Lakebase DSN from `LAKEBASE_DSN` (or `LAKEBASE_URL`); see
`src/phantom_census/lakebase/engine.py:build_engine_from_env` for the
resolution order.

## Optional: pgvector integration

`LP-INIT-004` creates a pgvector cosine index on
`cache.description_embeddings.embedding`. `postgres:16-alpine` does not ship
pgvector, so the migration logs a warning and continues; the index is not
created in that environment.

To exercise the index path end-to-end, set:

```bash
export TESTCONTAINERS_PGVECTOR=1
```

This switches `tests/lakebase/conftest.py` to the `pgvector/pgvector:pg16`
image. First run pulls the image (~250MB); subsequent runs reuse the layer
cache.

## Deploying to Databricks Apps

The Streamlit app deploys as a Databricks App via a project-root bundle
(`databricks.yml` + `app.yaml` + `requirements.txt`). The app is served by
the Apps runtime; it connects to Lakebase Postgres via the `postgres`
resource declared in the bundle.

### Prerequisites

- Databricks CLI configured with a profile that targets your workspace.
  This project assumes `--profile DEFAULT`. Verify:
  ```bash
  databricks auth describe --profile DEFAULT
  ```
- A Lakebase Postgres project named `phantom-census` with a `production`
  branch and a `databricks-postgres` database. Create it via the
  `databricks-lakebase` skill or the workspace UI before the first deploy.

### Deploy commands

```bash
# 1. Validate the bundle locally — should print "Validation OK!"
databricks bundle validate --profile DEFAULT

# 2. Upload source to the workspace and create/update the app resource
databricks bundle deploy --profile DEFAULT

# 3. Start (or restart) the app on the platform
databricks bundle run phantom_census --profile DEFAULT

# 4. Watch logs
databricks apps logs phantom-census --follow --profile DEFAULT
# (or `databricks apps get phantom-census --profile DEFAULT -o json`
#  to see app_status.state)
```

### Lakebase synced-tables setup (one-time per workspace)

After the first `bundle deploy`, run `docs/setup-synced-tables.sh` to
register the `phantom_census_lakebase` UC catalog, create the synced
tables, and grant the app service principal `SELECT` on the public
schema. The script is idempotent — re-run after notebook re-runs to
refresh synced tables.

### Customizing the host or Lakebase resource names

`databricks.yml` hardcodes the workspace host
(`dbc-f6aba42c-dca4.cloud.databricks.com`) and the Lakebase
branch/database resource names. To target a different workspace or
project, edit the `targets.default.workspace.host` value and the
`postgres_branch` / `postgres_database` defaults under `variables:`.

### Source upload size

The `sync.exclude` block in `databricks.yml` keeps `.venv/`, the test
suite, intent docs, and the obsolete `phantom-census-app/` React
scaffold out of the deploy bundle. Source-file upload is capped at 10 MB
per file by the Apps runtime; keep large data outside `data/` or
exclude it explicitly.

### CI: deploy on push via GitHub Actions

`.github/workflows/databricks-deploy.yml` runs on every push to the
`updated-specs` branch (the working branch for this project). It:

1. Installs `uv` and the dev extras
2. Runs `pytest tests` (Lakebase integration tests skip cleanly without
   Docker on the runner)
3. Validates the bundle (`databricks bundle validate`)
4. Deploys (`databricks bundle deploy`)
5. Restarts the app (`databricks bundle run phantom_census`)

#### Required GitHub repository secrets

The workflow authenticates with the workspace using OAuth M2M
(service-principal client credentials) — the local OAuth U2M flow
doesn't work in a non-interactive CI runner. Configure these under
**Repo → Settings → Secrets and variables → Actions**:

| Secret | Value |
|---|---|
| `DATABRICKS_HOST` | `https://dbc-f6aba42c-dca4.cloud.databricks.com` |
| `DATABRICKS_CLIENT_ID` | Service-principal application ID |
| `DATABRICKS_CLIENT_SECRET` | Service-principal OAuth secret |

#### Creating the service principal

From a logged-in CLI session on your laptop:

```bash
# 1. Create the SP — note BOTH the numeric `id` AND the UUID `applicationId`
# in the JSON output. They're used in different places.
databricks service-principals create \
  --display-name "phantom-census-ci" \
  --profile DEFAULT -o json

# 2. Generate an OAuth secret. Pass the numeric `id` (not the applicationId).
# The `secret` field in the response is shown ONCE — copy it straight
# into the GitHub repo secret.
databricks service-principal-secrets-proxy create <NUMERIC_ID_FROM_STEP_1> \
  --profile DEFAULT -o json
```

Then in GitHub:

- `DATABRICKS_CLIENT_ID` = the **`applicationId`** UUID from step 1
- `DATABRICKS_CLIENT_SECRET` = the **`secret`** field from step 2

#### Required SP permissions

Grant the service principal:

- **Workspace user** entitlement (so it can authenticate at all)
- **CAN_USE** on the SQL warehouse the app reads from (if applicable)
- **CAN_MANAGE** on the app resource (or on the workspace home folder
  the bundle deploys into — `/Workspace/Users/<SP>/.bundle/...`)
- **CAN_USE** on the Lakebase project + branch + database

For the hackathon scope, the simplest path is granting the SP the
**workspace admin** role; tighten down post-hackathon if the app moves
to production.

#### Local sanity check

To rehearse the CI auth path from your laptop without committing:

```bash
DATABRICKS_HOST=https://dbc-f6aba42c-dca4.cloud.databricks.com \
DATABRICKS_CLIENT_ID=<sp-client-id> \
DATABRICKS_CLIENT_SECRET=<sp-oauth-secret> \
DATABRICKS_AUTH_TYPE=oauth-m2m \
databricks bundle validate
```

If that prints `Validation OK!`, the GitHub Actions run will too.

## Optional: real Foundation Model adapter

The AI Evidence Layer (`existence_engine.ai_evidence_layer.maybe_render`)
and the planner-workspace Genie sidebar both accept an injectable adapter.
By default they fall back to deterministic template payloads — `token_usage`
on the verdict path stays at 0.

To wire a real Databricks Foundation Model API adapter:

```bash
export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
export DATABRICKS_TOKEN="dapi…"
# Adapter implementation: src/phantom_census/planner_workspace/fma_adapter.py
```

See that module's docstring for the contract the adapter must satisfy.
