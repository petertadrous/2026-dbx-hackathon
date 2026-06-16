# Overview
The Foundational Data Refresh (FDR) pipeline ingests data from public datasets and websites, applies a medallion architecture, performs GenAI-based information extraction, resolves primary keys across sources, and consolidates disparate records into a single unified row representing each entity.

---

## VF Facilities Table

Unity Catalog path: `databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities`

Row grain: one row per reported healthcare facility. The sample used in this project is ~10,000 rows, representing approximately 0.5% of the full national dataset.

### Columns

| Raw column | Canonical name (after rename) | Type | Notes |
|---|---|---|---|
| `unique_id` | `facility_id` | string | **Not enforced as unique** — duplicate values observed (same physical facility with spelling/address variants). Deduplicate on this key before processing. |
| `name` | `facility_name` | string | Free text. Contains embedded null bytes (`\x00`) in a subset of rows — strip before writing to any database. |
| `address_zipOrPostcode` | `pincode` | string | 6-digit India PIN code. Cast to string; treat as categorical, not numeric. Not always a valid 6-digit code. |
| `address_city` | `address_city` | string | City name as self-reported. Not normalized; varies in spelling and casing. |
| `address_stateOrRegion` | `address_stateOrRegion` | string | State/UT as self-reported. Does not reliably match the spatial-join district-to-state result. |
| `latitude` | `latitude` | float | WGS-84. Null or NaN for a subset of rows. Some coordinates are implausible (ocean, neighbouring country). |
| `longitude` | `longitude` | float | WGS-84. Same nullability as latitude. |
| `capability` | `capability` | array[string] | Self-declared service capabilities (e.g. `["Maternity", "NICU", "ICU"]`). 99.7% populated. Primary evidence field for existence detection. |
| `procedure` | `procedure` | array[string] | Specific procedures offered. 99.7% populated. |
| `equipment` | `equipment` | array[string] | Equipment available. 99.7% populated. |
| `description` | `description` | string | Free-text narrative. Median ~16 tokens — too short for reliable standalone duplicate detection; used as a supplement to the structured claim fields. May contain URLs (used by the Defender to count distinct registered domains). |
| `yearEstablished` | `yearEstablished` | int or string | Self-reported founding year. May be a future year, pre-independence year, or missing. Used by the temporal implausibility test. |

### Key data quality findings (observed at runtime)

- `unique_id` is not unique: same ID appears on 2–3 rows for some facilities (different address variants or transliterations). Fix: `drop_duplicates(subset=["facility_id"])` at ingestion.
- `name` / `facility_name` contains `\x00` bytes: causes `CHARACTER_NOT_IN_REPERTOIRE` in Spark and `ValueError` in psycopg2. Fix: strip null bytes before any write.
- `pincode` fan-out: a single PIN maps to multiple India Post post offices and potentially multiple districts — use `pin_centroids` (grouped centroid) for distance tests, not a raw join.
- `capability`, `procedure`, `equipment` arrive as arrays; concatenate for MinHash tokenisation.

See `docs/data-quality-notes.md` for the full issue log and mitigations.

Databricks Marketplace descriptions support only a small subset of markdown: headings (#, ##), bold (**), unordered lists (-), and plain paragraphs. Tables, code spans, horizontal rules, blockquotes, and nested formatting are stripped or broken. Here's a version written for that constraint:

Supplemental Data Sources: India Healthcare Geography & Public Health
Two public datasets for enriching India healthcare facility data. Use the PIN code directory for geographic lookup and address enrichment; use the NFHS-5 file to add district-level health and demographic context for demand-side analysis.
Both files are published under the Government Open Data License – India via data.gov.in.
Data quality note: These are real-world public-sector datasets. Expect inconsistent place-name casing, ambiguous postal mappings, missing coordinates, and suppressed values. Document how you handle uncertain matches and do not present inferred geography as exact unless verified.

India Post PIN Code Directory
File: india_post_pincode_directory.csv
Source: Open Government Data Platform India — All India Pincode Directory till last month
Source URL: https://www.data.gov.in/resource/all-india-pincode-directory-till-last-month
License: Government Open Data License – India (https://www.data.gov.in/Godl)
165,627 rows covering India's full postal geography. A PIN (Postal Index Number) is a 6-digit code similar to a ZIP or postcode. The file includes 19,586 unique PIN codes across 750 districts and 37 states and union territories.
Columns (11): circlename, regionname, divisionname, officename, pincode, officetype, delivery, district, statename, latitude, longitude
Office types: Branch Office (BO, ~140,000 rows), Post Office (PO, ~25,000 rows), Head Office (HO, ~800 rows).
Latitude and longitude are present but approximately 12,600 rows carry an NA value — do not assume every post office is geocoded.
Use cases:

* Enrich facility postcodes with district or state context
* Build geography lookup tables keyed by PIN code, post office, district, or state
* Explore postal geography ambiguity before joining to other datasets Important — row grain is post office, not PIN code. A single PIN can appear on multiple rows and may map to more than one district or state. A direct join on pincode will fan out rows unless you deduplicate or aggregate first. Always check cardinality before joining.

NFHS-5 District Health Indicators
File: nfhs5_district_health_indicators.csv
Source: National Family Health Survey 2019–21 district fact sheets via data.gov.in
Source URL: https://www.data.gov.in/catalog/national-family-health-survey-5-nfhs-5-india-districts-factsheet-data-provisional
Official fact sheets: https://www.nfhsiips.in/nfhsuser/nfhs5.php
License: Government Open Data License – India (https://www.data.gov.in/Godl)
706 district rows and 109 columns of indicators from India's National Family Health Survey (field period 2019–2021). This is the most comprehensive district-level public health dataset available for India at this geographic resolution.
Indicator groups: household conditions (electricity, water, sanitation, clean fuel, health insurance), maternal and reproductive health (ANC visits, institutional delivery, C-section rate, family planning), child health and vaccination (BCG, polio, DPT, MCV, rotavirus, vitamin A), nutrition (stunting, wasting, underweight, BMI, breastfeeding), anaemia, non-communicable diseases (blood sugar and blood pressure by sex), cancer screening, tobacco, alcohol.
Use cases:

* Add district-level health burden context to facility-level analysis
* Compare facility availability against population health indicators
* Build district rankings, demand-side maps, or planning dashboards
* Identify underserved districts where disease burden is high and facility coverage is low Data quality notes:
* Column names are long and human-readable — rename to snake_case before loading into a database or Delta table
* District and state names need normalization before joining to other sources; spelling and casing vary across datasets
* Asterisk (*) values are suppressed or unavailable — treat as NULL, not zero
* Parenthesized values such as (29.5) are estimates based on 25–49 unweighted cases and should be used with caution
* This dataset is NFHS-5 (2019–21). NFHS-6 (2023–24) data is available separately — if you use both, verify that indicator definitions and geographic units are comparable

Working with Location Data
To map facilities to administrative regions, use facility latitude and longitude with district or state boundary polygons from geoBoundaries (https://www.geoboundaries.org) or DataMeet India Maps (https://datameet.org). A point-in-polygon join assigns each facility to a district, enabling joins to the NFHS-5 file.
Suggested tools: GeoPandas and Shapely in Python, Databricks geospatial functions (ST_Contains, ST_Point), or QGIS for visual inspection.
String-matching district names across datasets is unreliable due to inconsistent spelling and transliteration. A spatial join on coordinates is more robust wherever facility coordinates are available.

