---
parent: high-level-design
prefix: DS
---

# Desert Scoring

## Context and Design Philosophy

The Desert Scoring component computes per-district desert scores in two states: `raw` (all facilities counted) and `adjusted` (phantom-verdicted facilities subtracted). It owns the `desert_scores` table that the Planner Workspace's pydeck `GeoJsonLayer` reads as its data prop.

The central constraint is demo reliability: the choropleth re-color on toggle must be sub-second and must not depend on live recomputation. The chosen approach is a **pydeck data-prop swap** — both raw and adjusted scores are loaded into Streamlit's session state on page open; toggling between views is a single line of Python that swaps which column the GeoJsonLayer's `get_fill_color` callback reads. No tile pre-rendering, no CSS opacity hacks, no live SQL on toggle. The pydeck layer regenerates GPU-side from the in-memory data, which is sub-second on 706 polygons.

A planner override (force-real / force-phantom) *does* trigger a recompute — but of a single district's score, not the full 706-district aggregate. The recompute path is: Lakebase override write → increment/decrement the district's `phantom_count` by 1 → recompute that district's `adjusted_desert_score` → mutate the in-memory data prop for that one district → pydeck re-renders just that polygon's fill. This is bounded and fast.

The toggle changes the *choropleth fill* only. Facility dots (drawn by the Planner Workspace's `ScatterplotLayer`) remain visible in both views — the desert score changes, the dataset's claimed facilities don't disappear. That tenet is owned by the Planner Workspace; desert scoring's contract is just to expose the two score columns side-by-side.

## Desert Score Formula

```
raw_desert_score(d) = 1 - (verified_facility_count(d) / max_facility_count_per_km2)
                       weighted by NFHS-5 disease burden(d)

adjusted_desert_score(d) = 1 - ((verified_facility_count(d) - phantom_count(d)) / max_facility_count_per_km2)
                            weighted by NFHS-5 disease burden(d)
```

Where:
- `verified_facility_count(d)` = count of facilities spatially joined to district `d` with `verdict != phantom`
- `phantom_count(d)` = count of facilities spatially joined to district `d` with `verdict = phantom`
- `max_facility_count_per_km2` = a per-state normalization constant computed at batch time as `max over all districts in the demo state of (verified_facility_count(d) / district_area_km2(d))`. For Maharashtra (the locked demo state) this resolves to a single float used for all districts in that state. The constant is recomputed each batch run from the current verdict set; demo-time it is a fixed value loaded into `st.session_state` at app open and not mutated by overrides (overrides shift one district's `phantom_count`, not the state-wide max).
- `NFHS-5 disease burden(d)` = 1 - (institutional_delivery_rate(d) / 100) for maternity capability; analogous indicators for other capabilities. **Fallback when suppressed:** if `institutional_delivery_rate(d)` is `*`-suppressed or null, substitute the state-level median rate and set `burden_imputed = true` on the `desert_scores` row (per spec DS-SCORE-005). The formula otherwise runs unchanged.
- Scores are normalized 0–1; higher = worse desert

**Score direction:** subtracting phantoms *increases* `adjusted_desert_score` relative to `raw_desert_score` — a district with phantom-inflated facility counts looks less underserved than it really is; removing the phantoms reveals the true gap. An override that marks a facility as phantom increases `phantom_count` → reduces `effective_facility_count` → raises the district's `adjusted_desert_score`. Implementers and tests must assert `adjusted > raw` when phantoms are present, not `adjusted < raw`.

The formula is intentionally simple and auditable. A planner who asks "how is this calculated?" gets a one-sentence answer.

## Choropleth Data Layer

The desert score data the Planner Workspace's `GeoJsonLayer` consumes is a single dataframe joined at app load:

```
districts_df = districts_geojson  # 706 ADM2 polygons (geometry + district_id)
                  .join(desert_scores, on="district_id")
                  # → district_id, district_name, geometry, raw_desert_score,
                  #   adjusted_desert_score, verified_facility_count, phantom_count
```

Both score columns are present side-by-side. The toggle is a Streamlit `st.session_state['view']` value (`"raw"` or `"adjusted"`); the pydeck `GeoJsonLayer.get_fill_color` callback reads `row[f"{view}_desert_score"]` and maps to a color via the shared red-intensity scale. No data round-trip; no pre-rendering; the GPU-side render is the only "redraw."

**Color scale:** red intensity for desert severity (white = 0.0, deep red = 1.0). Single shared scale across both view states so the color shift on toggle is interpretable as relative score difference, not scale change.

**Why not CSS opacity swap of pre-rendered tiles:** the original design pre-rendered two Folium HTML strings and toggled `display: block / none`. That approach lost click-into-region (Leaflet click events would need re-binding on toggle), required re-rendering both tile sets every time a planner override mutated a district, and added a `cache.tile_layers` table whose contents are a stale duplicate of `desert_scores`. The pydeck data-prop swap is simpler, has no duplicate state, and supports per-polygon mutation natively.

## Incremental Recompute on Override

When a planner override is saved to Lakebase, the recompute is **a Streamlit callback explicitly scheduled after the UPDATE commits — not a CDC trigger.** This guarantees the callback reads post-commit state and avoids any stale-read race window:

1. `team.planner_overrides` INSERT commits (ACID), returning the new `override_id`
2. `phantom_verdicts` UPDATE commits for the affected facility, setting `verdict` to the planner-directed value and `override_id` to the new override row
3. The Streamlit callback fires *after step 2 commits*. It reads the affected district's new `phantom_count` from `phantom_verdicts` (one SQL query, scoped to district)
4. The formula is applied in-process; the affected district's row in `districts_df` (in `st.session_state`) is mutated with the new `adjusted_desert_score` and `phantom_count`
5. Pydeck's `GeoJsonLayer` re-renders that polygon's fill from the mutated row
6. The district rank table re-sorts

This path operates on a single district and completes in < 1 second on the demo dataset. The full `districts_df` is never re-fetched; only one row mutates. **`max_facility_count_per_km2` is not recomputed on override** — overrides shift one district's `phantom_count`, not the state-wide max; recomputing would require scanning every district per override.

### Multi-capability facilities and per-capability score rows

`desert_scores` rows are keyed `(district_id, capability)`. A facility can claim multiple capabilities (e.g., a hospital with both maternity and ICU). When a planner overrides such a facility, **the override mutates `phantom_verdicts.verdict` once for the facility**, but the recompute callback must update **every `desert_scores` row whose capability the facility participates in**.

Concrete: facility F0123 claims both `maternity` and `icu` and is in district D. The planner force-phantoms F0123. The recompute callback updates two `desert_scores` rows: `(D, maternity)` and `(D, icu)`, decrementing each row's `verified_facility_count` and incrementing `phantom_count`. If the planner is currently viewing the maternity capability, only the `(D, maternity)` row's `adjusted_desert_score` change is rendered live; the `(D, icu)` change is persisted but not visually surfaced until the planner switches capabilities.

Implementers must read the facility's `capability` array from `vf_facilities` and iterate over the per-capability `desert_scores` rows for the facility's district — not assume a single row update.

## District Ranking Table

A companion ranked list shows all districts sorted by `adjusted_desert_score` descending. Updates on:
- **Toggle** — switches between `raw_desert_score` sort and `adjusted_desert_score` sort
- **Override save** — re-sorts with the recomputed score for the affected district (the override mutated `phantom_verdicts.verdict`, which mutated `phantom_count`, which mutated `adjusted_desert_score`)

The table also shows the rank delta (adjusted rank vs. raw rank) so planners can see which districts moved and by how much.

**What does *not* trigger a re-sort:** opening the AI Evidence Layer panel on a contested facility. The AI panel writes `phantom_verdicts.ai_recommendation` but does not change `verdict`; `phantom_count` is unchanged; the rank is unchanged. Re-sorts happen only on actual verdict mutations.

## Cross-segment data contracts

Desert scoring's contract to downstream consumers is exactly two artifacts:

1. `operational.desert_scores` — the per-`(district_id, capability)` table holding `raw_desert_score`, `adjusted_desert_score`, `verified_facility_count`, `phantom_count`, `burden_imputed`. Owned by this segment; written by batch and by override-recompute callbacks; read by the Planner Workspace's `GeoJsonLayer`.
2. The `districts_df` shape (joined geometry + scores) is constructed *in the Planner Workspace's app-load path* — desert scoring exposes the table; the workspace does the join. Any future migration of the join location does not change desert-scoring's contract.

**What desert scoring does NOT own:**
- The facility scatter data (the per-facility `(facility_id, lat, lon, verdict)` rows the Planner Workspace's `ScatterplotLayer` consumes for the green/ghost/yellow dots). That is a planner-workspace read directly from `vf_facilities` joined to `phantom_verdicts.verdict`. Desert scoring contributes the `verdict` column via the existence-engine pipeline but does not assemble the scatter dataframe.
- The toggle state (`st.session_state['view']`). Owned by the Planner Workspace; desert scoring just exposes both score columns side-by-side and lets the workspace decide which to render.
- The capability dropdown state. Same — owned upstream.

This boundary lets the Planner Workspace iterate on visual presentation (filter facilities by capability, change the scatter symbology, add layers) without touching `desert_scores`.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Choropleth re-color on toggle | Pydeck data-prop swap (single dataframe with both score columns; toggle reads which column to color by) | Pre-rendered Folium HTML strings + CSS opacity swap; live Lakebase CDC → reactive Streamlit push | Data-prop swap is sub-second on 706 polygons without duplicate state. CSS opacity of pre-rendered tiles loses click-into-region and requires re-rendering both tile sets on every override. CDC push on Free Edition is unverified. |
| Incremental override recompute | Single-district in-process mutation of `districts_df` row in `st.session_state` | Full 706-district batch re-run; full `districts_df` re-fetch from Lakebase | Single-district mutation is bounded (<1s) and avoids both a full re-batch and a full data-frame round-trip. The pydeck `GeoJsonLayer` re-renders only the mutated row. |
| Score formula | Deterministic, simple, one-sentence-explainable | ML-based facility quality score | Reproducibility and planner trust. A judge who asks "how is the score computed?" gets an immediate clear answer. |
| Pre-rendered tile cache | None (cut) | `cache.tile_layers` table holding pre-rendered Folium HTML strings per `(capability, layer_type)` | The cache duplicates `desert_scores` in a stale, harder-to-mutate form. Pydeck reads `desert_scores` directly; the cache table earns nothing. |

## Open Questions & Future Decisions

### Resolved
1. ✅ Toggle uses pydeck data-prop swap, not pre-rendered tile cache. Rationale: simpler state, supports per-polygon mutation, no duplicate `cache.tile_layers` to keep in sync.

### Deferred
1. Whether to add a secondary NFHS indicator selector (e.g., child vaccination rate for Track 1 capability alignment) — deferred to post-MVP if time allows.
2. Whether to normalize scores to a 0–100 "Desert Index" for presentation — deferred; currently 0–1 float is shown with 2 decimal places.

## References

- `docs/high-level-design.md` — system architecture
- `docs/intent/existence-engine/existence-engine-design.md` — upstream verdict source
- `docs/intent/lakebase-persistence/lakebase-persistence-design.md` — `desert_scores` table schema
