---
parent: high-level-design
prefix: DS
---

## Desert Scoring — EARS Specs

### Score Computation (Batch)

- [ ] **DS-SCORE-001**: The system shall compute `raw_desert_score` for each district as `1 - (verified_facility_count / max_facility_count_per_km2)` weighted by the district's NFHS-5 disease burden indicator, normalized to [0, 1].
- [ ] **DS-SCORE-002**: The system shall compute `adjusted_desert_score` for each district using `verified_facility_count - phantom_count` in place of `verified_facility_count` in DS-SCORE-001.
- [ ] **DS-SCORE-003**: The system shall store both `raw_desert_score` and `adjusted_desert_score` per district in `public.desert_scores`, along with `verified_facility_count`, `phantom_count`, `contested_count`, `total_count`, `raw_rank`, `adjusted_rank`, and `rank_shift`.
- [ ] **DS-SCORE-004**: For the maternity capability view, the system shall use the NFHS-5 institutional-delivery rate as the disease-burden weight; for other capability views, the system shall use the analogous NFHS-5 indicator specified in the capability-indicator mapping config.
- [ ] **DS-SCORE-005**: When a district's NFHS-5 indicator is suppressed (`*`) or missing, the system shall use the state-level median as the weight for that district and record a `burden_imputed = true` flag in `public.desert_scores`.
- [ ] **DS-SCORE-006**: The system shall compute `rank_shift` per district per capability as `raw_rank − adjusted_rank` and store it in `public.desert_scores`; a positive value indicates the district became more underserved after phantom removal.

### Tile Layer Pre-rendering

- [ ] **DS-TILE-001**: The system shall pre-render one adjusted tile layer per supported capability (e.g., maternity, ICU) at batch time, producing a `(capability, 'adjusted')` keyed Folium choropleth HTML string stored as a row in `public.tile_layers`.
- [ ] **DS-TILE-001a**: The system shall pre-render the following capabilities at minimum: maternity. Additional capabilities are additive; the app degrades gracefully to maternity-only if other capability layers are missing.
- [ ] **DS-TILE-002**: The adjusted tile layer shall use red-intensity color scale (white = 0.0, deep red = 1.0) proportional to `adjusted_desert_score`.
- [ ] **DS-TILE-003**: The system shall load the pre-rendered adjusted tile layer for the active capability from `public.tile_layers` as an HTML string at app startup.
- [ ] **DS-TILE-005**: At batch time, before persisting the tile layer set, the system shall verify that every `(capability, layer_type)` pair has exactly one non-degenerate tile — HTML present, at least a minimum size, and containing a Folium/Leaflet structural marker — and shall fail the batch with an error naming any missing or degenerate tile, rather than persisting a partial `tile_layers` set.

### Phantom-Impact CircleMarkers

- [ ] **DS-MARKER-001**: After building the base choropleth, the system shall overlay orange `folium.CircleMarker` elements on the top-30 districts by `rank_shift`, computed at batch pre-render time; the threshold is the 80th percentile of `rank_shift` across districts for that capability, with a minimum threshold of 15.
- [ ] **DS-MARKER-002**: Each CircleMarker radius shall be proportional to `rank_shift`, clamped to a minimum of 5 px and a maximum of 16 px; districts with no geometry or empty geometry shall be skipped.
- [ ] **DS-MARKER-003**: Each CircleMarker tooltip shall include the district name, `rank_shift` value, and `phantom_count` so planners hovering the marker see why it is flagged.

### District Rank Table

- [ ] **DS-RANK-001**: The system shall display a district ranking table alongside the choropleth, sorted by `adjusted_desert_score` descending.
- [ ] **DS-RANK-002**: The system shall display a `rank_shift` column showing `raw_rank − adjusted_rank` for each district; positive values indicate districts newly exposed as more underserved after phantom removal.

### Incremental Override Recompute

- [ ] **DS-OVR-001**: When a planner override is saved to Lakebase (affecting one facility), the system shall recompute `adjusted_desert_score` for only the affected district using the updated `phantom_count`.
- [ ] **DS-OVR-002** *(stretch)*: After DS-OVR-001 commits, the app shall re-render only the affected district's polygon in the Folium adjusted layer by updating that district's GeoJSON feature color property and triggering a targeted component refresh; the full layer HTML string shall not be re-rendered. *In the hackathon build the affected district's row is updated in the scores frame in-process and the next batch tile-render pass picks up the change; targeted GeoJSON-feature mutation is post-MVP.*
- [ ] **DS-OVR-003**: The incremental recompute triggered by DS-OVR-001 shall complete and update the UI within 1 second of the override save.
- [ ] **DS-OVR-004**: The system shall update the district ranking table to reflect the recomputed score immediately after DS-OVR-001 completes.

### Phantom Counter Display

- [ ] **DS-CTR-001**: The system shall display a "phantoms removed" counter on the choropleth view showing the total count of facilities with `verdict = phantom` for the currently selected capability and region.
- [ ] **DS-CTR-003**: The system shall display `token_usage: 0` in the choropleth header panel, reflecting that no LLM calls were made during the scoring pipeline.
