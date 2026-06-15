---
parent: high-level-design
prefix: DS
---

# Desert Scoring

## Context and Design Philosophy

The Desert Scoring component computes per-district desert scores in two states: `raw` (all facilities counted) and `adjusted` (phantom-verdicted facilities subtracted). It also pre-renders the choropleth tile layers consumed by the Planner Workspace.

The central constraint is demo reliability: the choropleth redraw must be instantaneous and must not depend on live computation or Free Edition CDC behavior. The chosen approach is CSS opacity swap of pre-rendered tile layers — the two layers are both loaded on page start; toggling switches which is visible. The "live recompute" feel comes from the district rank counter updating (a fast Lakebase read), not from re-running the scoring pipeline.

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

The formula is intentionally simple and auditable. A planner who asks "how is this calculated?" gets a one-sentence answer.

## Tile Layer Pre-rendering

Two Folium choropleth layers are pre-rendered at batch time:
1. `raw_layer` — districts colored by `raw_desert_score`
2. `adjusted_layer` — districts colored by `adjusted_desert_score`

Both layers are embedded in the Streamlit app as HTML strings. On toggle, the app switches `display: block / none` between the two layers. No server round-trip; no live Lakebase read for the toggle itself.

**Color scale:** Red intensity for desert severity (white = no desert, deep red = worst desert). Consistent between both layers so the color shift on toggle is interpretable as relative change, not scale change.

## Incremental Recompute on Override

When a planner override is saved to Lakebase:

1. `planner_overrides` write commits (ACID)
2. A Streamlit callback reads the single affected district's new `phantom_count` from `desert_scores`
3. The formula is applied in-process (no batch re-run)
4. The affected district's polygon color is updated in the already-loaded Folium layer
5. The district rank table re-sorts

This path operates on a single district and completes in < 1 second on the demo dataset.

## District Ranking Table

A companion ranked list shows all districts sorted by `adjusted_desert_score` descending. Updates on:
- Toggle (switches between `raw_desert_score` sort and `adjusted_desert_score` sort)
- Override save (re-sorts with new score for the affected district)

The table also shows the rank delta (adjusted rank vs. raw rank) so planners can see which districts moved and by how much.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Choropleth redraw | CSS opacity swap of pre-rendered layers | Live Lakebase CDC → reactive Streamlit push | CDC on Free Edition is unverified; pre-rendered swap achieves identical visual effect with no runtime dependency risk. |
| Incremental override recompute | Single-district in-process recompute | Full 706-district batch re-run | Single-district is bounded (<1s); full re-batch is too slow for a live demo. |
| Score formula | Deterministic, simple, one-sentence-explainable | ML-based facility quality score | Reproducibility and planner trust. A judge who asks "how is the score computed?" gets an immediate clear answer. |
| Tile format | Folium GeoJSON overlay as HTML string | External tile server | Free Edition has no external tile server. In-process Folium produces identical output. |

## Open Questions & Future Decisions

### Resolved
1. ✅ Toggle uses CSS opacity swap, not Streamlit re-render. Rationale: avoids any risk of Streamlit re-render latency during the demo.

### Deferred
1. Whether to add a secondary NFHS indicator selector (e.g., child vaccination rate for Track 1 capability alignment) — deferred to post-MVP if time allows.
2. Whether to normalize scores to a 0–100 "Desert Index" for presentation — deferred; currently 0–1 float is shown with 2 decimal places.

## References

- `docs/high-level-design.md` — system architecture
- `docs/intent/existence-engine/existence-engine-design.md` — upstream verdict source
- `docs/intent/lakebase-persistence/lakebase-persistence-design.md` — `desert_scores` table schema
