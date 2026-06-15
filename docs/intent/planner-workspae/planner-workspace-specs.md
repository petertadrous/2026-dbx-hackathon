---
parent: high-level-design
prefix: PW
---

## Planner Workspace — EARS Specs

### Choropleth View

- [ ] **PW-MAP-001**: The system shall display an India choropleth map using pre-rendered Folium tile layers, with districts colored by red-intensity proportional to the active desert score.
- [ ] **PW-MAP-002**: The system shall display a capability selector (dropdown) above the choropleth; changing the selection shall reload the pre-rendered tile layers for the selected capability.
- [ ] **PW-MAP-003**: The system shall display a two-state toggle labeled "Raw" and "Adjusted" above the choropleth; the active state shall be visually distinguished.
- [ ] **PW-MAP-004**: When the planner activates the "Adjusted" toggle, the system shall swap to the adjusted tile layer using CSS visibility change with no server-side recompute.
- [ ] **PW-MAP-005**: The system shall display a "Phantoms removed: N" counter in the map header, where N is the count of phantom-verdicted facilities for the currently selected capability.
- [ ] **PW-MAP-006**: The system shall display a "token_usage: 0" indicator in the map header.
- [ ] **PW-MAP-007**: When the planner activates the Adjusted toggle, the phantoms-removed counter shall animate from 0 to N over 0.5 seconds.

### District Side Panel

- [ ] **PW-PANEL-001**: When the planner clicks a district on the choropleth, the system shall display a side panel with the district's name, `adjusted_desert_score`, `raw_desert_score`, raw rank, adjusted rank, and rank delta.
- [ ] **PW-PANEL-002**: The side panel shall list up to 5 example phantom facilities for the selected district, each showing the facility name, its top-failed test name, and a one-line summary of the failing evidence.
- [ ] **PW-PANEL-003**: Each phantom example in the side panel shall include a link or expandable row revealing the full test evidence (India Post row, MinHash cluster members, NFHS-5 indicator value, etc.) drawn from `operational.facility_existence_tests`.
- [ ] **PW-PANEL-004**: The side panel shall remain visible and updated when the planner toggles between raw and adjusted views.

### Override Panel

- [ ] **PW-OVR-001**: When the planner clicks "Override" on a specific phantom in the side panel, the system shall display an override panel with the facility name, current verdict, and the primary failing test.
- [ ] **PW-OVR-002**: The override panel shall require a non-empty reason note before enabling the "Force Real" and "Force Phantom" action buttons.
- [ ] **PW-OVR-003**: When the planner submits an override, the system shall write the override to `team.planner_overrides` with fields: `facility_id`, `override_type` (`force-real` | `force-phantom`), `reason_note`, `planner_id`, and `overridden_at`.
- [ ] **PW-OVR-004**: After an override is saved (PW-OVR-003), the system shall update the facility's verdict badge in the side panel to reflect the override (e.g., "force-real (overridden)").
- [ ] **PW-OVR-005**: After an override is saved, the system shall trigger the DS-OVR-001 single-district recompute and update the choropleth and ranking table within 1 second.

### Export

- [ ] **PW-EXP-001**: When the planner clicks "Export Plan", the system shall write a CKAN-compatible CSV to the configured S3 watched prefix containing: district name, state, `raw_desert_score`, `adjusted_desert_score`, `phantom_count`, `verified_facility_count`, and any override notes for the session.
- [ ] **PW-EXP-002**: When the planner clicks "Export Plan", the system shall POST a JSON payload to the mock HMIS webhook endpoint containing the top-5 priority districts (by `adjusted_desert_score`) and their scores.
- [ ] **PW-EXP-003**: If the S3 write or HMIS webhook POST fails, the system shall display an error message in the side panel without disrupting the rest of the app state.

### Scenario Persistence

- [ ] **PW-SCEN-001**: When the planner clicks "Save Scenario", the system shall prompt for a scenario name and write the current session state to `team.saved_scenarios` in Lakebase: `scenario_name`, `capability`, `region_filter`, `override_set` (JSONB array of override IDs), `planner_notes`, and `saved_at`.
- [ ] **PW-SCEN-002**: On app load, the system shall display a list of saved scenarios for the current planner session; selecting one shall restore the saved capability, region filter, and override set.
- [ ] **PW-SCEN-003**: When a saved scenario is loaded, the system shall apply the stored override set to `operational.phantom_verdicts` and recompute affected district scores before rendering the choropleth.
- [ ] **PW-SCEN-004**: A restored scenario shall produce an identical choropleth state to the state when the scenario was saved, given the same underlying phantom verdicts.
