# Phantom Census — User Guide

## What it does

Phantom Census detects fraudulent ("phantom") healthcare facilities in India's facility registry and redraws district healthcare desert maps after subtracting them. Planners and NGO officers use it to allocate budgets against districts that are genuinely underserved — not just underserved on paper due to ghost entries.

**The key insight:** every existing desert map counts all claimed facilities. Phantom Census subtracts the ones that fail existence checks before ranking districts.

---

## Opening the app

Navigate to the deployed Databricks App URL. The app loads in three progressive stages — you will see content appear as each stage completes:

1. **~1–2 s** — Summary metric cards populate (facilities scored, phantoms removed, contested count)
2. **~2–3 s** — District ranking table populates
3. **~3–5 s** — India choropleth map renders

---

## Header controls

| Control | What it does |
|---------|-------------|
| **Capability dropdown** | Switches the entire view to a different clinical capability: Maternity, ICU, Emergency, Trauma, or NICU. All scores, the map, and the ranking table re-load for the selected capability. |
| **Raw / Adjusted toggle** | **Raw** — district scores based on all claimed facilities. **Adjusted** — district scores after removing phantoms. Switch between them to see rank shifts. |

---

## Summary metric cards

Four cards at the top show national-level totals for the selected capability:

| Card | Meaning |
|------|---------|
| **Facilities scored** | Total facilities that claimed this capability |
| **Phantoms removed** | Facilities flagged `phantom` by the existence engine |
| **Contested** | Facilities with ambiguous evidence — neither confirmed real nor phantom |
| **token_usage: 0** | All verdicts are fully deterministic — zero LLM calls at detection time |

---

## The choropleth map

The map shows all of India's ~700 districts coloured by healthcare desert score for the selected capability. **Darker red = more underserved.**

### Interacting with the map

- **Click any district** — the map zooms in to that district, highlights its polygon, and the right-hand panel populates with district details and phantom evidence.
- **Hover** — a lighter highlight previews the district before clicking.
- **Pan and zoom** — standard mouse/touch controls. The map returns to national view when you switch capability or reload.
- **Raw / Adjusted toggle** — swaps the colour layer between raw and phantom-adjusted scores without reloading the map.

Districts with no facilities claiming the selected capability are shown in grey.

---

## District ranking table

Below the map, the ranking table lists districts sorted by desert score (most underserved first) for the current view mode.

| Column | Meaning |
|--------|---------|
| **District** | District name |
| **State** | State / union territory |
| **Score** | Desert score 0–1 (higher = more underserved) |
| **Rank shift** | Change in rank position between Raw and Adjusted views. A positive shift means the district moved up the "needs attention" list once phantoms were removed. |
| **Phantoms** | Number of phantom facilities in this district for the selected capability |

**Click any row** — selects that district. The right-hand panel updates with district details and the map zooms to highlight that district.

The currently selected row is highlighted.

---

## District detail panel (right sidebar)

Appears when a district is selected. Shows:

### Scores and ranks

| Field | Meaning |
|-------|---------|
| **Raw score** | Desert score counting all claimed facilities |
| **Adjusted score** | Desert score after subtracting phantoms |
| **Raw rank** | Position in the raw ranking (1 = most underserved) |
| **Adjusted rank** | Position in the adjusted ranking |

A large gap between raw rank and adjusted rank means this district has many phantom facilities inflating its apparent supply.

### Phantom examples

Up to 10 phantom facilities in this district are listed. Each card shows:
- **Facility name** (or ID if name is missing)
- **Primary failed test** — the existence check that flagged this facility (e.g. `pin-reverse-lookup`, `minhash-near-duplicate`)
- **Overridden** — shown if a planner has previously overridden this facility's verdict

**Click a facility card** to expand its full test evidence in the panel below.

---

## Test evidence panel

Appears when a phantom facility is selected. Shows the result of each existence test:

| Test | What it checks |
|------|---------------|
| `pin-reverse-lookup` | Does the claimed PIN code's GPS coordinates match the facility's own lat/lon? A mismatch of >50 km is a hard veto. |
| `minhash-near-duplicate` | Is this facility's capability/procedure/equipment text a near-duplicate (Jaccard ≥ 0.9) of 2 or more other facilities? Suggests copy-paste fabrication. |
| `spatial-district-mismatch` | Does the PIN-claimed district match the district determined by spatial join of the facility's coordinates? |
| `nfhs-outcome-inconsistency` | Does the district's NFHS-5 institutional delivery rate contradict a maternity capability claim? |
| `temporal-implausibility` | Is the year established in the future, or implausibly early combined with high-acuity claims? |

Results: **pass** (green), **fail** (red), **not-applicable** (grey — facility lacks the data needed for this test), **indeterminate** (insufficient evidence either way).

---

## Overriding a verdict

Planners can manually correct any verdict. Overrides are **append-only** — the original verdict is preserved in the audit trail.

1. Select a district and click a phantom facility to set the facility ID in the **Override verdict** card.
2. Type a **reason note** (required — this is your audit trail entry).
3. Click **Force Real** or **Force Phantom**.

After saving, the phantom list for the current district refreshes immediately to reflect the override. The district's adjusted desert score will update on the next pipeline run.

> **Override audit trail**: every override records who submitted it, when, and the reason note. Overrides cannot be deleted.

---

## Saved scenarios

Use **Save scenario** to preserve your current session:

1. Enter a scenario name (e.g. "Q3 Bihar Maternity Audit").
2. Optionally add notes.
3. Click **Save scenario**.

Saved scenarios appear in the list above the save form. They capture the selected capability and region context. Use them to resume a planning session or share your view with a colleague.

---

## Workflow: typical planning session

```
1. Select capability (e.g. Maternity)
2. View Adjusted map — identify red clusters that differ from Raw view
3. Click a district with a large rank shift in the table
4. Review phantom examples — check which tests failed
5. Click a facility → read test evidence
6. If a facility is clearly legitimate, add a reason note → Force Real
7. Save the session as a named scenario
8. Switch to another capability and repeat
```

---

## Understanding desert scores

Desert score = 1 − (facility count / maximum facility count in the same state), normalised within state.

- **0.0** = best-served district in its state
- **1.0** = completely unserved relative to state peers

**Raw score** uses all claimed facilities. **Adjusted score** uses only verified facilities (real + contested). The difference reveals how much phantom inflation was distorting the picture.

---

## Frequently asked questions

**Why does a district show phantoms but still have a low adjusted score?**
A low score means the district is relatively well-served even after subtraction. Phantom count and desert score are independent — a district can have many phantoms but still have enough real facilities to rank low on the desert scale.

**What does "contested" mean?**
The existence engine could not definitively confirm or deny the facility's existence — typically because too few test signals were available (e.g. missing coordinates, no PIN code). Contested facilities are excluded from the "verified" count used in the adjusted score.

**Why is token_usage always 0?**
All phantom verdicts are produced by deterministic rule-based tests (PIN lookup, MinHash, spatial join, NFHS-5 comparison, temporal check). No language model is involved in any verdict. The token counter is displayed to make this explicit.

**How often does the data refresh?**
Scores and tiles are pre-computed by the offline pipeline. Run the `phantom-census-pipeline` Databricks job and redeploy the app to refresh after data changes.
