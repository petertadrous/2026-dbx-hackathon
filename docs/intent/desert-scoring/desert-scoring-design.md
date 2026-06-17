---
parent: high-level-design
prefix: DS
---

# Desert Scoring

## Context and Design Philosophy

The Desert Scoring component computes per-district desert scores in two states: `raw` (all facilities counted) and `adjusted` (phantom-verdicted facilities subtracted). It pre-renders the choropleth tile layer consumed by the Planner Workspace and computes per-district rank shifts that drive the phantom-impact markers.

The central constraint is demo reliability: the choropleth must load instantly without live computation. A single pre-rendered adjusted tile layer is served; phantom-impact CircleMarkers are baked into that tile at batch time, overlaying the top-30 districts by `rank_shift` (districts most exposed by phantom removal).

A planner override (force-real / force-phantom) *does* trigger a recompute — but of a single district's score, not the full 706-district aggregate. The recompute path is: Lakebase override write → increment/decrement the district's `phantom_count` by 1 → recompute that district's `adjusted_desert_score` → update the pre-rendered tile for that one district. This is bounded and fast.

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
- `NFHS-5 disease burden(d)` = 1 - (institutional_delivery_rate(d) / 100) for maternity capability; analogous indicators for other capabilities
- Scores are normalized 0–1; higher = worse desert

**Score direction:** subtracting phantoms *increases* `adjusted_desert_score` relative to `raw_desert_score` — a district with phantom-inflated facility counts looks less underserved than it really is; removing the phantoms reveals the true gap. An override that marks a facility as phantom increases `phantom_count` → reduces `effective_facility_count` → raises the district's `adjusted_desert_score`. Implementers and tests must assert `adjusted > raw` when phantoms are present, not `adjusted < raw`.

**Rank shift:** `rank_shift(d) = raw_rank(d) − adjusted_rank(d)`. A positive value means the district jumped up the "underserved" list after phantom removal — phantoms were hiding its true desert status. Stored in `desert_scores` alongside the scores; used to drive CircleMarker sizing on the tile.

The formula is intentionally simple and auditable. A planner who asks "how is this calculated?" gets a one-sentence answer.

## Tile Layer Pre-rendering

One Folium choropleth layer is pre-rendered at batch time:

- `adjusted_layer` — districts colored by `adjusted_desert_score` (red intensity, white = 0.0, deep red = 1.0)

The layer is embedded in the app as an HTML string and loaded at startup. No toggle; the adjusted view is the primary (and only) choropleth view.

**Phantom-impact CircleMarkers:** After the base choropleth is built, orange `folium.CircleMarker` overlays are added for the top-30 districts by `rank_shift` (threshold: 80th percentile of `rank_shift`, minimum 15). Marker radius is proportional to `rank_shift` (clamped 5–16 px). This encodes both desert severity (choropleth color) and phantom distortion (circle size/presence) in a single view without a toggle.

**Completeness guard (DS-TILE-005):** The batch render and Lakebase load both validate the tile set before persisting — every `(capability, layer_type)` pair must have exactly one non-degenerate tile. Partial renders fail loudly rather than shipping silently.

## Incremental Recompute on Override

When a planner override is saved to Lakebase:

1. `planner_overrides` write commits (ACID)
2. A server-side callback reads the single affected district's new `phantom_count` from `desert_scores`
3. The formula is applied in-process (no batch re-run)
4. The affected district's row in the ranking table re-sorts with the new score

This path operates on a single district and completes in < 1 second on the demo dataset.

## District Ranking Table

A companion ranked list shows all districts sorted by `adjusted_desert_score` descending. Updates on:
- Override save (re-sorts with new score for the affected district)

The table shows `rank_shift` (adjusted rank vs. raw rank) so planners can see which districts moved and by how much.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Choropleth view | Single adjusted view with CircleMarkers | Two-layer CSS opacity swap (raw ↔ adjusted) | Single view communicates both desert severity and phantom distortion without two nearly-identical choropleths that are hard to compare. CircleMarker size encodes rank_shift directly. Removes the toggle that required loading and switching two large HTML blobs. |
| Phantom-impact encoding | Orange CircleMarkers on top-30 rank-shift districts, baked into tile HTML | Separate overlay toggle; client-side rendering | Baking into the pre-rendered tile avoids any client-side Leaflet wiring complexity and works with the existing HTML-string tile approach. |
| Incremental override recompute | Single-district in-process recompute | Full 706-district batch re-run | Single-district is bounded (<1s); full re-batch is too slow for a live demo. |
| Score formula | Deterministic, simple, one-sentence-explainable | ML-based facility quality score | Reproducibility and planner trust. A judge who asks "how is the score computed?" gets an immediate clear answer. |
| Tile format | Folium GeoJSON overlay as HTML string | External tile server | Free Edition has no external tile server. In-process Folium produces identical output. |

## Open Questions & Future Decisions

### Resolved
1. ✅ Single adjusted tile with CircleMarkers replaces two-layer toggle. Rationale: one view communicates more than two similar choropleths; rank_shift is better encoded as a marker than as a color-diff that requires mental subtraction.

### Deferred
1. Whether to add a secondary NFHS indicator selector (e.g., child vaccination rate for Track 1 capability alignment) — deferred to post-MVP if time allows.
2. Whether to normalize scores to a 0–100 "Desert Index" for presentation — deferred; currently 0–1 float is shown with 2 decimal places.

## References

- `docs/high-level-design.md` — system architecture
- `docs/intent/existence-engine/existence-engine-design.md` — upstream verdict source
- `docs/intent/lakebase-persistence/lakebase-persistence-design.md` — `desert_scores` table schema
