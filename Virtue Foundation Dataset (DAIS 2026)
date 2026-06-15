# Overview
The Foundational Data Refresh (FDR) pipeline ingests data from public datasets and websites, applies a medallion architecture, performs GenAI-based information extraction, resolves primary keys across sources, and consolidates disparate records into a single unified row representing each entity.

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

