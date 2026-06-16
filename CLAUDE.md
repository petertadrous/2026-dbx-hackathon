# Phantom Census

Production code: `src/phantom_census/`. Tests: `tests/`. Design docs: `docs/intent/`.

## LID

- Mode: Full
- Version: 1

LID-managed segments (each with `docs/intent/<segment>/<segment>-design.md` + `<segment>-specs.md`):

- `existence-engine` — Prosecutor/Defender/Adjudicator, batch deterministic phantom detection.
- `lakebase-persistence` — operational schema, engine writer, app readers, override/scenario writers.
- `desert-scoring` — per-district raw + phantom-adjusted scores, pre-rendered Folium tile layers, single-district recompute.
- `planner-workspae` — Streamlit + Folium app: choropleth, side panel, override modal, scenario save/restore.

## Conventions

- `@spec EE-…`, `@spec LP-…`, `@spec DS-…`, `@spec PW-…` annotations at the entry point of the behavior's implementation graph (module/function level), not on every helper.
- Tests live under `tests/<segment>/`. Each test method tagged with the EARS IDs it exercises.
- Postgres-only for Lakebase. Tests use `testcontainers[postgres]` (ephemeral Docker). When the Docker daemon is unreachable, Lakebase tests skip.
- LLMs are not in any verdict or scoring path. `token_usage: 0` is a load-bearing claim — keep it true.
