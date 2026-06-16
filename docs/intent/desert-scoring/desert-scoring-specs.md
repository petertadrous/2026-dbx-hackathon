---
parent: high-level-design
prefix: DS
---

## Desert Scoring — EARS Specs

### Score Computation (Batch)

- [ ] **DS-SCORE-001**: The system shall compute `raw_desert_score` for each district as `1 - (verified_facility_count / max_facility_count_per_km2)` weighted by the district's NFHS-5 disease burden indicator, normalized to [0, 1].
- [ ] **DS-SCORE-002**: The system shall compute `adjusted_desert_score` for each district using `verified_facility_count - phantom_count` in place of `verified_facility_count` in DS-SCORE-001.
- [ ] **DS-SCORE-003**: The system shall store both `raw_desert_score` and `adjusted_desert_score` per district in `operational.desert_scores`, along with `verified_facility_count`, `phantom_count`, and the raw formula inputs.
- [ ] **DS-SCORE-004**: For the maternity capability view, the system shall use the NFHS-5 institutional-delivery rate as the disease-burden weight; for other capability views, the system shall use the analogous NFHS-5 indicator specified in the capability-indicator mapping config.
- [ ] **DS-SCORE-005**: When a district's NFHS-5 indicator is suppressed (`*`) or missing, the system shall use the state-level median as the weight for that district and record a `burden_imputed = true` flag in `operational.desert_scores`.

### Tile Layer Pre-rendering

- [ ] **DS-TILE-001**: The system shall pre-render one raw tile layer and one adjusted tile layer per supported capability (e.g., maternity, ICU) at batch time, producing a `(capability, layer_type)` keyed set of Folium choropleth HTML strings stored as rows in `cache.tile_layers`.
- [ ] **DS-TILE-001a**: The system shall pre-render the following capabilities at minimum: maternity. Additional capabilities are additive; the app degrades gracefully to maternity-only if other capability layers are missing.
- [ ] **DS-TILE-002**: Both tile layers shall use the same red-intensity color scale (white = 0.0, deep red = 1.0) so toggle-induced color changes are interpretable as relative score differences on the same scale.
- [ ] **DS-TILE-003**: The system shall load both pre-rendered tile layers for the active capability from `cache.tile_layers` as HTML strings at Streamlit app startup.
- [ ] **DS-TILE-004**: When the planner toggles between raw and adjusted views, the system shall switch layer visibility using CSS `display: block / none` without issuing any server-side recompute request.
- [ ] **DS-TILE-005**: At batch time, before persisting the tile layer set, the system shall verify that every `(capability, layer_type)` pair has exactly one non-degenerate tile — HTML present, at least a minimum size, and containing a Folium/Leaflet structural marker — and shall fail the batch with an error naming any missing or degenerate tile, rather than persisting a partial `tile_layers` set.

### District Rank Table

- [ ] **DS-RANK-001**: The system shall display a district ranking table alongside the choropleth, sorted by the currently active score (`raw_desert_score` when in raw view; `adjusted_desert_score` when in adjusted view), descending.
- [ ] **DS-RANK-002**: The system shall display a rank-delta column showing each district's adjusted rank minus its raw rank, so planners can see which districts moved and by how much.
- [ ] **DS-RANK-003**: When the planner toggles views, the ranking table shall re-sort to the active score column without a page reload.

### Incremental Override Recompute

- [ ] **DS-OVR-001**: When a planner override is saved to Lakebase (affecting one facility), the system shall recompute `adjusted_desert_score` for only the affected district using the updated `phantom_count`.
- [ ] **DS-OVR-002** *(stretch)*: After DS-OVR-001 commits, the Streamlit app shall re-render only the affected district's polygon in the Folium adjusted layer by updating that district's GeoJSON feature color property and triggering a targeted Streamlit component refresh; the full layer HTML string shall not be re-rendered. *In the hackathon build the affected district's row is updated in the scores frame in-process and the next batch tile-render pass picks up the change; targeted GeoJSON-feature mutation is post-MVP.*
- [ ] **DS-OVR-003**: The incremental recompute triggered by DS-OVR-001 shall complete and update the UI within 1 second of the override save.
- [ ] **DS-OVR-004**: The system shall update the district ranking table to reflect the recomputed score immediately after DS-OVR-001 completes.

### Phantom Counter Display

- [ ] **DS-CTR-001**: The system shall display a "phantoms removed" counter on the choropleth view showing the total count of facilities with `verdict = phantom` for the currently selected capability and region.
- [ ] **DS-CTR-002** *(stretch)*: When the planner toggles to the adjusted view, the counter shall animate from 0 to the final phantom count over 0.5 seconds. *In the hackathon build the counter renders the final value immediately on toggle; explicit animation timing is post-MVP.*
- [ ] **DS-CTR-003**: The system shall display `token_usage: 0` in the choropleth header panel, reflecting that no LLM calls were made during the scoring pipeline.
