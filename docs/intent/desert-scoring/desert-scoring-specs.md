---
parent: high-level-design
prefix: DS
---

## Desert Scoring — EARS Specs

### Score Computation (Batch)

- [ ] **DS-SCORE-001**: The system shall compute `raw_desert_score` for each `(district_id, capability)` pair as `1 - (verified_facility_count / max_facility_count_per_km2)` weighted by the district's NFHS-5 disease burden indicator, normalized to [0, 1], where `district_id` is the geoBoundaries ADM2 `shapeID`.
- [ ] **DS-SCORE-002**: The system shall compute `adjusted_desert_score` for each `(district_id, capability)` pair using `verified_facility_count - phantom_count` in place of `verified_facility_count` in DS-SCORE-001.
- [ ] **DS-SCORE-003**: The system shall store `raw_desert_score`, `adjusted_desert_score`, `verified_facility_count`, `phantom_count`, `district_name`, `state_name`, and `updated_at` per `(district_id, capability)` row in `operational.desert_scores`.
- [ ] **DS-SCORE-004**: For the maternity capability view, the system shall use the NFHS-5 institutional-delivery rate as the disease-burden weight; for other capability views, the system shall use the analogous NFHS-5 indicator specified in the capability-indicator mapping config.
- [ ] **DS-SCORE-005**: When a district's NFHS-5 indicator is suppressed (`*`) or missing, the system shall use the state-level median as the weight for that district and record a `burden_imputed = true` flag in `operational.desert_scores`.
- [ ] **DS-SCORE-006**: The system shall compute `max_facility_count_per_km2` once per state at batch time as the maximum over all districts in that state of `(verified_facility_count(d) / district_area_km2(d))` and shall persist this constant for use by the score formula; this constant shall not be recomputed on planner overrides.

### Choropleth Data Layer (Pydeck Data-Prop Swap)

- [ ] **DS-MAP-001**: The system shall expose both `raw_desert_score` and `adjusted_desert_score` as columns on the `operational.desert_scores` row for each `(district_id, capability)` pair so that the Planner Workspace's `GeoJsonLayer` can swap which column is read for fill-color without reissuing a Lakebase read.
- [ ] **DS-MAP-002**: Both score columns exposed by DS-MAP-001 shall be normalized to the same [0, 1] range so the Planner Workspace can apply a single shared red-intensity color scale (white = 0.0, deep red = 1.0) across raw and adjusted views.
- [ ] **DS-MAP-003**: The system shall not pre-render Folium HTML choropleth tiles for raw or adjusted views; the choropleth render is owned by the Planner Workspace's pydeck `GeoJsonLayer` reading `operational.desert_scores` directly.

### Incremental Override Recompute

- [ ] **DS-OVR-001**: The desert-scoring module shall expose an override-recompute callback function which the Planner Workspace's override save handler invokes after the `UPDATE` to `operational.phantom_verdicts.verdict` for a single `facility_id` commits (not before); the callback shall recompute `adjusted_desert_score` and `phantom_count` for every `operational.desert_scores` row whose `(district_id, capability)` matches the affected facility's spatial-join district and any of the facility's claimed capabilities.
- [ ] **DS-OVR-002**: The override-recompute callback in DS-OVR-001 shall update only the affected `operational.desert_scores` rows; it shall not re-fetch or recompute scores for unaffected districts and shall not recompute `max_facility_count_per_km2`.
- [ ] **DS-OVR-003**: After DS-OVR-001 commits the recomputed `desert_scores` rows, the Streamlit app shall mutate the corresponding rows in the in-memory `districts_df` held in `st.session_state` and the pydeck `GeoJsonLayer` shall re-render the affected polygons' fill from the mutated data.
- [ ] **DS-OVR-004**: The override-recompute path described by DS-OVR-001 through DS-OVR-003 shall complete and update the rendered choropleth within 1 second of the planner's override save action on the demo dataset (Maharashtra, ~10k facilities, ~36 districts).
- [ ] **DS-OVR-005**: The override-recompute callback shall preserve the existing `burden_imputed` value on each affected `operational.desert_scores` row; overrides shall not flip `burden_imputed` because the NFHS-5 imputation is a per-district data property unaffected by override-driven count changes.
- [ ] **DS-OVR-006**: When the AI Evidence Layer writes `phantom_verdicts.ai_recommendation` or `phantom_verdicts.ai_recommendation_evidence_state` without changing `phantom_verdicts.verdict`, the override-recompute callback shall not fire and `operational.desert_scores` shall not be updated.

### Multi-Capability Facility Override Handling

- [ ] **DS-MULTICAP-001**: When a planner override mutates `phantom_verdicts.verdict` for a facility that claims more than one capability (e.g., `maternity` and `icu`), the override-recompute callback shall iterate over every capability in the facility's `vf_facilities.capability` array and shall update the `operational.desert_scores` row for each `(facility_district_id, capability)` pair the facility participates in.
- [ ] **DS-MULTICAP-002**: When the planner is currently viewing a specific capability (per `st.session_state['capability']`) and the override affects multiple capabilities, the choropleth re-render shall surface the recomputed score change only for the actively viewed capability; recomputed rows for other capabilities shall be persisted to Lakebase but shall not produce a visible re-render until the planner selects that capability.
- [ ] **DS-MULTICAP-003**: When `st.session_state['capability']` changes (planner picks a different value in the capability dropdown), the system shall re-fetch `operational.desert_scores` for the new capability from Lakebase and shall replace `st.session_state['districts_df']` with the post-fetch rows; in-memory mutations from prior overrides are persisted in Lakebase and surface naturally via this re-fetch.

### District Rank Table

- [ ] **DS-RANK-001**: The system shall display a district ranking table alongside the choropleth, sorted by the currently active score (`raw_desert_score` when in raw view; `adjusted_desert_score` when in adjusted view), descending.
- [ ] **DS-RANK-002**: The system shall display a rank-delta column showing each district's adjusted rank minus its raw rank, so planners can see which districts moved and by how much.
- [ ] **DS-RANK-003**: When the planner toggles views, the ranking table shall re-sort to the active score column without a page reload.
- [ ] **DS-RANK-004**: When a planner override mutates `phantom_verdicts.verdict` for a facility, the ranking table shall re-sort to reflect the recomputed `adjusted_desert_score` for the affected district within the same 1-second window as DS-OVR-004.
- [ ] **DS-RANK-005**: When the AI Evidence Layer writes `phantom_verdicts.ai_recommendation` or `ai_recommendation_evidence_state` without changing `verdict`, the district ranking table shall not re-sort.

### Phantom Counter Display

- [ ] **DS-CTR-001**: The system shall display a "phantoms removed" counter on the choropleth view showing the total count of facilities with `phantom_verdicts.verdict = phantom` for the currently selected capability and region.
- [ ] **DS-CTR-002**: When the planner toggles `st.session_state['view']` to `"adjusted"`, the counter shall animate from 0 to the final phantom count over 0.5 seconds.
