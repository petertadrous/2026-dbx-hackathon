---
parent: high-level-design
prefix: PW
---

# Planner Workspace

## Context and Design Philosophy

The Planner Workspace is the Databricks App (Streamlit) that state planning commissioners and NGO program officers interact with. It presents the choropleth, the district drill-down, the override panel, and the export controls.

The design constraint is: **zero training needed for a non-technical user to grasp the demo in 3 minutes.** Every screen element serves one of four jobs: (1) show the map and the phantom-impact markers, (2) explain a specific phantom with evidence and an optional AI brief, (3) let the planner override a verdict, (4) export and persist the session.

The workspace has no analysis-mode navigation, no configuration panels, no settings tabs. It is a workflow, not a dashboard.

## Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Phantom Census         Capability: [Maternity ▼]                       │
│  Phantoms removed: 1,247   token_usage: 0                               │
├────────────────────────────────────┬────────────────────────────────────┤
│                                    │  Nalanda District                  │
│   INDIA CHOROPLETH                 │  Adjusted desert score: 0.84       │
│   (Folium, red-intensity)          │  Raw score: 0.61 · Rank: 7th → 2nd│
│   ● orange circles = rank movers   │                                    │
│                                    │  PHANTOM EXAMPLES (shown)          │
│   [click any district]             │  ● Phantom A: PIN says Patna,      │
│                                    │    lat/lon says Gaya (148km off)   │
│                                    │    [India Post row ↗]              │
│                                    │  ● Phantom B: 0.97 Jaccard match  │
│                                    │    with 14 other facilities        │
│                                    │  ● Phantom C: Claims maternity;    │
│                                    │    NFHS inst-delivery flat 3 yrs   │
│                                    │                                    │
│                                    │  AI VERIFICATION BRIEF             │
│                                    │  [Generate Brief]                  │
│                                    │  → streams 4-section analysis      │
│                                    │                                    │
│                                    │  [Override] [Export Plan]          │
│                                    │  [Save Scenario]                   │
└────────────────────────────────────┴────────────────────────────────────┘
```

## AI Verification Brief

When the planner selects a district, an "AI Verification Brief" card appears in the side panel with a "Generate Brief" button. On click, the app calls `GET /api/planner/districts/:id/brief?capability=<cap>`, which:

1. Queries Lakebase for the district's stats (`raw_rank`, `adjusted_rank`, `rank_shift`, `phantom_count`, `contested_count`, `verified_facility_count`) and the full list of phantom/contested facilities with their test-failure signatures.
2. Builds a structured prompt encoding the evidence and passes it to the Llama 3.3 70B Foundation Model API endpoint (`databricks-meta-llama-3-3-70b-instruct`) via `DatabricksAdapter` from AppKit.
3. Streams the response back to the client as SSE (`data: {"text": "..."}` events).

The brief always contains four sections:

- **Phantom Pattern** — what failure modes dominate and what they suggest about root cause (administrative fraud vs. facility closure vs. survey error).
- **Priority Targets** — the three contested or borderline facilities most worth dispatching a field team to, with specific reasoning from their test failures.
- **Rank-Shift Risk** — if all contested facilities are confirmed phantom, how the district's adjusted rank changes and what the policy implication is.
- **Ministry Recommendation** — one concrete, data-grounded action for the state health ministry.

The LLM makes no verdict decisions. It synthesizes existing deterministic verdicts + test evidence into a human-readable planning document. `token_usage: 0` in the header remains accurate — it counts verdict-pipeline tokens only.

The brief clears when the planner selects a different district or changes the capability. After generation the button label changes to "Regenerate".

## Override Panel

When the planner clicks "Override" on a specific facility:

```
┌──────────────────────────────────────────────────┐
│  Override Verdict: Phantom A (facility_id: F1234) │
│                                                   │
│  Current verdict: phantom (PIN veto)              │
│  Reason note (required): [                      ] │
│                                                   │
│  [Force Real]  [Force Phantom]  [Cancel]          │
└──────────────────────────────────────────────────┘
```

- Reason note is required before either button is enabled.
- On save: writes to `team.planner_overrides`, triggers DS-OVR-001 recompute.
- After save: the district's adjusted score updates in the choropleth within 1 second; the facility's verdict badge in the side panel changes from "phantom" to "force-real (overridden)" or vice versa.

## Export Controls

Two export actions available from the side panel:

1. **Export Plan** — writes a CKAN-compatible CSV to a pre-configured S3 watched prefix. The CSV contains the district ranking table with `raw_desert_score`, `adjusted_desert_score`, `phantom_count`, and any planner overrides applied in this session. Also fires the mock HMIS webhook with a structured priority delta payload.

2. **Save Scenario** — persists the current session to Lakebase: selected capability, active overrides, planner notes, region filters. Named by the planner. Scenario is reloadable on future visits.

## Scenario Persistence

On page load, the app checks for saved scenarios associated with the current planner session. If one is found, it offers to restore it ("Resume scenario: Q3 Bihar Maternity Audit?"). Restored scenarios replay the same override set and region filters, producing an identical choropleth state.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Override requires reason note | Mandatory text field | Optional note | Required note is the human-in-the-loop mechanism the hackathon brief explicitly requires. It also creates a defensible audit trail for a planning commissioner who may be questioned about their decisions. |
| Single-capability view at a time | Capability dropdown selects one | Multi-capability overlay | Multi-capability overlay complicates the choropleth color encoding beyond what a 3-minute demo can explain. Single capability keeps the thesis visible: "we subtracted X phantoms from maternity, and here's what changed." |
| Choropleth view | Single adjusted view with CircleMarkers | Two-state Raw/Adjusted toggle | One view communicates both desert severity (color) and phantom distortion (circle size) without requiring the planner to mentally compare two nearly-identical choropleths. |
| AI brief model | Llama 3.3 70B via Databricks Foundation Model API | Claude Opus 4.8 (same platform) | Llama 3.3 70B is available under the Free Edition fair-use quota; Claude Opus 4.8 has a rate limit of 0 on Free Edition. |
| AI brief streaming | SSE from Express route | Batch response | Streaming gives the planner visible progress on a ~5-second generation; a batch response with no feedback feels frozen. |
| Export triggers mock HMIS webhook | Yes, on Export Plan click | User-configurable webhook endpoint | A hard-coded mock endpoint fires reliably in the demo; a user-configurable one introduces a setup step that wastes demo time. |
| Scenario naming | Planner provides name | Auto-generated timestamp | Named scenarios are visually recognizable in the reload list; timestamps require the planner to remember what they did when. |

## Open Questions & Future Decisions

### Resolved
1. ✅ Override reason note is mandatory (cannot save without it). Rationale: matches the "human-in-the-loop with audit trail" requirement of the hackathon brief.
2. ✅ Token counter displays `0` in the header, not hidden. Rationale: the "deterministic core, zero tokens" framing is a differentiator; make it visible. Note: the counter counts verdict-pipeline tokens; the AI Verification Brief does consume tokens but is opt-in and clearly labeled.
3. ✅ Single adjusted view with CircleMarkers replaces Raw/Adjusted toggle. Rationale: one view is clearer than two similar choropleths; rank_shift is better encoded as a visual marker than as a color shift requiring mental subtraction.

### Deferred
1. Multi-region comparison view (show two states side-by-side) — deferred to stretch.
2. Planner-configurable Jaccard threshold slider — deferred; adds UI complexity with low demo value.

## References

- `docs/high-level-design.md` — target user definitions and non-goals
- `docs/intent/desert-scoring/desert-scoring-design.md` — tile layers and incremental recompute
- `docs/intent/lakebase-persistence/lakebase-persistence-design.md` — override and scenario table schemas
