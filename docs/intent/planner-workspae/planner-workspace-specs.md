---
parent: high-level-design
prefix: PW
---

## Planner Workspace — EARS Specs

### App Shell

- [ ] **PW-SHELL-001**: The system shall present the workspace as a single Streamlit page with three tabs labeled "Map", "Budget Reallocation", and "Audit Queue"; only one tab's content shall be rendered at a time.
- [ ] **PW-SHELL-002**: The system shall display a capability dropdown above the tabs; the dropdown's options shall be populated from `SELECT DISTINCT capability FROM operational.desert_scores` at app load and cached in `st.session_state['available_capabilities']`.
- [ ] **PW-SHELL-003**: When only one capability is available in `st.session_state['available_capabilities']`, the capability dropdown shall be rendered disabled.
- [ ] **PW-SHELL-004**: The system shall display an activation-gate badge in the header reading "Activation gate: N contested · est. cost ≤ $X" where N is the count of facilities with `phantom_verdicts.verdict = contested` for the active capability and X is `N × $0.005` formatted to two decimal places.
- [ ] **PW-SHELL-005**: The system shall display a footer reading "Determinism owns the math; AI owns the evidence; human owns the decision." verbatim and persistently across all tabs.
- [ ] **PW-SHELL-006**: The system shall render the Genie sidebar in Streamlit's left-rail `st.sidebar` so that it persists across all three tabs without re-render.

### Tab-Switch State Preservation

- [ ] **PW-TAB-001**: The system shall persist per-tab state (Map view's `selected_district` and `selected_facility`; Audit Queue's scroll position and pagination cursor; Budget Reallocation's in-progress edits) under the keys `st.session_state['map']`, `st.session_state['audit_queue']`, and `st.session_state['budget']` respectively.
- [ ] **PW-TAB-002**: When the planner switches away from a tab and back to the same tab in the same session, the system shall restore that tab's prior state from its `st.session_state` key.
- [ ] **PW-TAB-003**: The system shall persist shared cross-tab state (`view`, `capability`, `selected_district` cross-references) at the top level of `st.session_state` so tab switches do not reset shared selections.

### Map View

- [ ] **PW-MAP-001**: The system shall display a choropleth using a pydeck `GeoJsonLayer` whose `get_fill_color` callback reads `row[f"{view}_desert_score"]` from the in-memory `districts_df` (joined from `operational.desert_scores` and the geoBoundaries ADM2 geometry on `shapeID`), where `view` is the current value of `st.session_state['view']`.
- [ ] **PW-MAP-002**: The system shall display a two-state toggle labeled "Raw" and "Adjusted" above the choropleth; activating the toggle shall set `st.session_state['view']` to `"raw"` or `"adjusted"` and shall not issue any Lakebase read.
- [ ] **PW-MAP-003**: The system shall render facility markers as a pydeck `ScatterplotLayer` with `get_fill_color` derived from each facility's `phantom_verdicts.verdict`: green for `real`, grey for `phantom` (rendered as a ghost marker), yellow for `contested`.
- [ ] **PW-MAP-004**: When the planner toggles `st.session_state['view']` between `"raw"` and `"adjusted"`, the `ScatterplotLayer`'s `get_fill_color` and visibility shall be unchanged; phantom and contested markers shall remain visible in both views.
- [ ] **PW-MAP-005**: The system shall display a "Phantoms removed: N" counter in the map header where N is the count of phantom-verdicted facilities for the currently selected capability.
- [ ] **PW-MAP-006**: When the planner activates the Adjusted toggle, the phantoms-removed counter shall animate from 0 to N over 0.5 seconds.

### District Side Panel

- [ ] **PW-PANEL-001**: When the planner clicks a district on the choropleth, the system shall display a side panel with the district's name, `adjusted_desert_score`, `raw_desert_score`, raw rank, adjusted rank, and rank delta.
- [ ] **PW-PANEL-002**: The side panel shall list up to 5 phantom-verdicted or contested facilities for the selected district, ranked by leverage (`mortality_burden_percentile × population_proxy × phantom_density`), each row collapsed by default and showing the facility name, verdict badge, and one-line summary of the top-failed test.
- [ ] **PW-PANEL-003**: Each phantom example in the side panel shall include a link or expandable row revealing the full test evidence (India Post row, MinHash cluster members, NFHS-5 indicator value, embedding-drift cosine value, etc.) drawn from `operational.facility_existence_tests`.
- [ ] **PW-PANEL-004**: The side panel shall remain visible and updated when the planner toggles between raw and adjusted views.
- [ ] **PW-PANEL-005**: For facilities with `phantom_verdicts.verdict = contested`, expanding the facility row shall trigger the AI Evidence Layer per the existence-engine LLD's lookup logic; for facilities with any other `verdict`, expanding the row shall not invoke the AI Evidence Layer.

### AI Advisory Block

- [ ] **PW-AI-001**: When a contested facility's row is expanded and the AI Evidence Layer produces (or returns cached) a recommendation, the system shall display an inline AI Advisory block within that row showing `recommendation`, `confidence`, `reasoning`, and a link to the cited evidence rows.
- [ ] **PW-AI-002**: When the rendered recommendation has `source = "template-fallback"`, the AI Advisory block shall append "(template fallback)" next to the confidence label.
- [ ] **PW-AI-003**: When `phantom_verdicts.override_id IS NOT NULL` AND `phantom_verdicts.ai_recommendation IS NOT NULL`, the AI Advisory block shall render the existing recommendation marked as "historical advisory".
- [ ] **PW-AI-004**: When `phantom_verdicts.override_id IS NOT NULL` AND `phantom_verdicts.ai_recommendation IS NULL`, the AI Advisory block shall not render.
- [ ] **PW-AI-005**: The AI Advisory block shall not render for facilities whose `verdict` is not `contested`.

### Override Panel

- [ ] **PW-OVR-001**: When the planner clicks "Override" on a specific facility in the side panel, the system shall display an override panel showing the facility name, `facility_id`, current `verdict`, `adjudicator_verdict`, `rescue_applied` summary (signals fired or "none"), and AI advisory summary (if `verdict = contested`, otherwise "n/a").
- [ ] **PW-OVR-002**: The override panel shall require a non-empty `reason_note` text field before enabling the "Force Real" and "Force Phantom" action buttons.
- [ ] **PW-OVR-003**: When the planner submits an override, the system shall execute the write sequence in order: (1) INSERT into `team.planner_overrides`; (2) UPDATE `phantom_verdicts.verdict` and `override_id` for the affected facility; (3) fire the desert-score override-recompute Streamlit callback.
- [ ] **PW-OVR-004**: After PW-OVR-003 commits, the system shall update the facility's verdict badge in the side panel to display "force-real (overridden)" or "force-phantom (overridden)" with the planner's reason note shown on hover.
- [ ] **PW-OVR-005**: After PW-OVR-003 commits, the choropleth and ranking table shall update to reflect the recomputed scores within 1 second of the override save (per desert-scoring DS-OVR-004).
- [ ] **PW-OVR-006**: After PW-OVR-003 commits, the Audit Queue and Budget Reallocation views' rankings shall be invalidated so that switching to those tabs displays the post-override state.
- [ ] **PW-OVR-007**: Opening the Override Panel shall not invoke the AI Evidence Layer; the Override Panel reads only `phantom_verdicts.ai_recommendation` as already persisted. When `verdict = contested` AND `ai_recommendation IS NULL`, the panel shall display "AI advisory: not yet computed (expand row to fetch)" rather than firing FMA.

### Budget Reallocation View

- [ ] **PW-BUDGET-001**: The Budget Reallocation view shall display two pie charts side by side: a "Before" pie chart of `team.budget_allocations.allocated_inr` per district for the active capability and quarter, and a "Recommended" pie chart of the deterministically-computed re-allocation.
- [ ] **PW-BUDGET-002**: The system shall compute the recommended re-allocation as follows: sort districts by `adjusted_desert_score × NFHS-5 burden weight × population_proxy` descending; compute each district's fair share as `total_budget × normalized_score / sum(normalized_scores)`; cap each district's recommended allocation at `min(fair_share, prior_allocation × 2.5)`.
- [ ] **PW-BUDGET-003**: The Budget Reallocation view shall display a table with columns `district_name`, `current_inr`, `recommended_inr`, `delta_inr`, sorted by `mortality_burden_percentile × phantom_density(district)` descending.
- [ ] **PW-BUDGET-004**: When the planner clicks "Export revised allocation CSV", the system shall write a CSV to the configured S3 prefix containing columns `district_id, district_name, current_inr, recommended_inr, delta_inr, justification`, where `justification` is a one-line string referencing the adjusted desert score and current rank.
- [ ] **PW-BUDGET-005**: The recommended re-allocation produced by PW-BUDGET-002 shall not be written back to `team.budget_allocations`; the table holds historical allocations only.
- [ ] **PW-BUDGET-006**: When a planner override mutates `desert_scores` for a district in scope of the recommendation, the recommendation table and pie charts shall re-render to reflect the recomputed scores; if a district's recommended-allocation rank shifts by ≥ 3 positions, the row shall briefly highlight to draw attention.
- [ ] **PW-BUDGET-007**: The Budget Reallocation view shall not invoke any LLM or AI Evidence Layer call.

### Audit Queue View

- [ ] **PW-AUDIT-001**: The Audit Queue view shall display the top-50 facilities with `phantom_verdicts.verdict = phantom` for the active capability, sorted by leverage where `leverage = mortality_burden_percentile × population_proxy × phantom_density(district)`; ties shall be broken by the count of failed tests in `phantom_verdicts.test_outcome_vector` (more fails = higher rank).
- [ ] **PW-AUDIT-002**: Each row in the audit queue table shall display `rank`, `facility_name`, `district_name`, `pincode`, `latitude,longitude`, and a comma-separated list of failed test names.
- [ ] **PW-AUDIT-003**: When the planner clicks "Export inspector worksheet PDF", the system shall generate a print-ready PDF in-process (using `reportlab` or equivalent) containing one row per top-50 facility, with the district, PIN, GPS coordinates, and a checkbox list of the failed tests; no external service calls shall be made.
- [ ] **PW-AUDIT-004**: When a planner override mutates `phantom_verdicts.verdict` for a facility, the audit queue shall rebuild from the current `phantom_verdicts` rows so that overridden-to-real facilities drop out and overridden-to-phantom facilities are inserted; the rebuild shall complete within 1 second on the demo dataset.
- [ ] **PW-AUDIT-005**: The Audit Queue view shall not invoke any LLM or AI Evidence Layer call.

### Genie Sidebar

- [ ] **PW-GENIE-001**: The Genie sidebar shall expose natural-language SQL access to the following tables in read-only mode: `operational.desert_scores`, `operational.phantom_verdicts`, `operational.facility_existence_tests`, `team.budget_allocations`, `team.planner_overrides`, `vf_facilities`. Reads on `team.planner_overrides` shall not be filtered by `planner_id`; all overrides ever written are visible to any Genie session as institutional audit visibility.
- [ ] **PW-GENIE-002**: The Genie sidebar shall not have read access to `cache.claim_minhash`, `cache.description_embeddings`, or `team.saved_scenarios`.
- [ ] **PW-GENIE-003**: The Genie sidebar shall not have write access to any Lakebase table; all Genie-issued SQL shall be SELECT-only.
- [ ] **PW-GENIE-004**: The Genie sidebar shall be visible across all three tabs in Streamlit's left-rail `st.sidebar` and shall be collapsible per Streamlit's default behavior.

### Map View Export — Scenario CSV + HMIS Webhook

- [ ] **PW-EXP-001**: When the planner clicks "Export Plan", the system shall write a CKAN-compatible CSV to the configured S3 watched prefix containing: district name, state, `raw_desert_score`, `adjusted_desert_score`, `phantom_count`, `verified_facility_count`, and any override notes for the session.
- [ ] **PW-EXP-002**: When the planner clicks "Export Plan", the system shall POST a JSON payload to the mock HMIS webhook endpoint containing the top-5 priority districts (by `adjusted_desert_score`) and their scores.
- [ ] **PW-EXP-003**: If the S3 write or HMIS webhook POST fails, the system shall display an error message in the side panel without disrupting the rest of the app state.
- [ ] **PW-EXP-004**: The three export deliverables (revised allocation CSV per PW-BUDGET-004, inspector worksheet PDF per PW-AUDIT-003, scenario CSV + HMIS webhook per PW-EXP-001/002) shall be independent; clicking one shall not invalidate or modify the artifacts produced by the others.
- [ ] **PW-EXP-005**: Each export button shall display a small `(last exported: HH:MM)` timestamp next to the button after a successful export so the planner can see staleness as subsequent overrides are made.

### Scenario Persistence

- [ ] **PW-SCEN-001**: When the planner clicks "Save Scenario", the system shall prompt for a scenario name and write the current session state to `team.saved_scenarios` in Lakebase: `scenario_name`, `capability`, `region_filter`, `override_set` (JSONB array of override IDs), `planner_notes`, and `saved_at`.
- [ ] **PW-SCEN-002**: On app load, the system shall display a list of saved scenarios for the current planner session; selecting one shall restore the saved capability, region filter, and override set.
- [ ] **PW-SCEN-003**: A restored scenario shall produce an identical choropleth state to the state when the scenario was saved, given the same underlying phantom verdicts.
