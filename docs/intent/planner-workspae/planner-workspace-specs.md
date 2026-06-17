---
parent: high-level-design
prefix: PW
---

## Planner Workspace — EARS Specs

### Choropleth View

- [ ] **PW-MAP-001**: The system shall display an India choropleth map using the pre-rendered Folium adjusted tile layer, with districts colored by red-intensity proportional to `adjusted_desert_score`.
- [ ] **PW-MAP-002**: The system shall display a capability selector (dropdown) above the choropleth; changing the selection shall reload the pre-rendered adjusted tile layer for the selected capability.
- [ ] **PW-MAP-005**: The system shall display a "Phantoms removed: N" counter in the map header, where N is the count of phantom-verdicted facilities for the currently selected capability.
- [ ] **PW-MAP-006**: The system shall display a "token_usage: 0" indicator in the map header, reflecting that the verdict and scoring pipeline makes no LLM calls.
- [ ] **PW-MAP-008**: The choropleth tile shall include orange CircleMarkers on the top-30 districts by `rank_shift`, baked into the pre-rendered HTML at batch time (see DS-MARKER-001–003).

### District Side Panel

- [ ] **PW-PANEL-001**: When the planner clicks a district on the choropleth, the system shall display a side panel with the district's name, `adjusted_desert_score`, `raw_desert_score`, `raw_rank`, `adjusted_rank`, and `rank_shift`.
- [ ] **PW-PANEL-002**: The side panel shall list up to 10 example phantom facilities for the selected district, each showing the facility name, its top-failed test name, and verdict.
- [ ] **PW-PANEL-003**: Each phantom example in the side panel shall include a link or expandable row revealing the full test evidence (India Post row, MinHash cluster members, NFHS-5 indicator value, etc.) drawn from `public.facility_existence_tests`.
- [ ] **PW-PANEL-004**: The side panel shall remain visible and updated when the planner changes the capability selector.

### AI Verification Brief

- [ ] **PW-BRIEF-001**: When a district is selected, the system shall display an "AI Verification Brief" card in the side panel with a "Generate Brief" button.
- [ ] **PW-BRIEF-002**: When the planner clicks "Generate Brief", the system shall call `GET /api/planner/districts/:id/brief?capability=<cap>` and stream the response via SSE, rendering text incrementally as each `data: {"text": "..."}` event arrives.
- [ ] **PW-BRIEF-003**: The generated brief shall contain exactly four sections: Phantom Pattern, Priority Targets, Rank-Shift Risk, and Ministry Recommendation, produced by the Llama 3.3 70B Foundation Model API (`databricks-meta-llama-3-3-70b-instruct`) using the district's phantom list and test-failure evidence as input.
- [ ] **PW-BRIEF-004**: The brief shall clear when the planner selects a different district or changes the capability; the "Generate Brief" button shall change to "Regenerate" after a brief has been generated for the current district.

### Override Panel

- [ ] **PW-OVR-001**: When the planner clicks "Override" on a specific phantom in the side panel, the system shall display an override panel with the facility name, current verdict, and the primary failing test.
- [ ] **PW-OVR-002**: The override panel shall require a non-empty reason note before enabling the "Force Real" and "Force Phantom" action buttons.
- [ ] **PW-OVR-003**: When the planner submits an override, the system shall write the override to `team.planner_overrides` with fields: `facility_id`, `override_type` (`force-real` | `force-phantom`), `reason_note`, `planner_id`, and `overridden_at`.
- [ ] **PW-OVR-004**: After an override is saved (PW-OVR-003), the system shall update the facility's verdict badge in the side panel to reflect the override (e.g., "force-real (overridden)").
- [ ] **PW-OVR-005**: After an override is saved, the system shall trigger the DS-OVR-001 single-district recompute and update the choropleth and ranking table within 1 second.

### Export

> **Deferred (post-MVP).** Per scope decision recorded in the project plan,
> the Export Plan surface is not in scope for the hackathon build. The three
> specs below remain as the contract for a future cascade and are intentionally
> uncovered by tests or code.

- [ ] **PW-EXP-001** *(deferred)*: When the planner clicks "Export Plan", the system shall write a CKAN-compatible CSV to the configured S3 watched prefix containing: district name, state, `raw_desert_score`, `adjusted_desert_score`, `phantom_count`, `verified_facility_count`, and any override notes for the session.
- [ ] **PW-EXP-002** *(deferred)*: When the planner clicks "Export Plan", the system shall POST a JSON payload to the mock HMIS webhook endpoint containing the top-5 priority districts (by `adjusted_desert_score`) and their scores.
- [ ] **PW-EXP-003** *(deferred)*: If the S3 write or HMIS webhook POST fails, the system shall display an error message in the side panel without disrupting the rest of the app state.

### Scenario Persistence

- [ ] **PW-SCEN-001**: When the planner clicks "Save Scenario", the system shall prompt for a scenario name and write the current session state to `team.saved_scenarios` in Lakebase: `scenario_name`, `capability`, `region_filter`, `override_set` (JSONB array of override IDs), `planner_notes`, and `saved_at`.
- [ ] **PW-SCEN-002**: On app load, the system shall display a list of saved scenarios for the current planner session; selecting one shall restore the saved capability, region filter, and override set.
- [ ] **PW-SCEN-003**: When a saved scenario is loaded, the system shall apply the stored override set to `public.phantom_verdicts` and recompute affected district scores before rendering the choropleth.
- [ ] **PW-SCEN-004**: A restored scenario shall produce an identical choropleth state to the state when the scenario was saved, given the same underlying phantom verdicts.
