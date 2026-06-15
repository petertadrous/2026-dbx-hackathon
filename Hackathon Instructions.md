# Databricks Hackathon Hub
All information related to the Databricks Apps & Agents Hackathon for Good can be found here: developers.databricks.com/hackathon

Announcements and questions related to credits, the Databricks platform, or Virtue Foundation can be found in the hackathon's Discord during event hours: discord.com/invite/bedRGCjFq

 
### Challenge
You are given 10,000 messy records of healthcare facilities across India. Each record includes structured fields such as location and specialties, plus uneven free-text descriptions of claimed capabilities, procedures, equipment, and services.

Build a Databricks App that helps a non-technical healthcare planner, NGO coordinator, or analyst turn this messy data into decisions they can trust.

Your app should extract useful structure from the records, show evidence for its conclusions, communicate uncertainty honestly, and let users save or revise their work.

 
### Dataset
The provided dataset contains 10,000 Indian healthcare facility records and 51 columns.

All records include facility name, state, city, latitude, longitude, controlled specialties, a description, and source URLs; 9,996 records include a postcode. The extracted evidence fields are noisy, repetitive, and unevenly supported:

Field	Coverage
description	100%
capability	99.7%
procedure	92.5%
equipment	77.0%
numberDoctors	36.4%
capacity	25.2%
yearEstablished	47.8%
Useful evidence appears across description, capability, procedure, equipment, specialties, and source_urls. Teams should treat these fields as claims to verify rather than ground truth.

## Requirements
### Core Requirements
* Run as a Databricks App on Free Edition.
* Use the provided facility dataset.
* Support a clear non-technical user workflow.
* Cite the underlying facility text for any important claim, recommendation, score, or ranking.
* Communicate uncertainty instead of presenting weak evidence as fact.
* Persist user actions such as notes, overrides, shortlists, scenarios, or review decisions.

### Tracks (Pick One)
#### Track 1: Facility Trust Desk
* Question: Can this facility actually do what it claims?
* Build an app that evaluates facility claims for capabilities such as ICU, maternity, emergency, oncology, trauma, or NICU. For each facility and capability, produce a trust signal such as strong evidence, partial evidence, weak or suspicious evidence, or no claim.
* Minimum workflow: a planner selects a capability and region, sees ranked facilities, expands a facility to inspect citations, and can override the assessment with a note.

#### Track 2: Medical Desert Planner
* Question: Where are the highest-risk gaps in care, and how confident are we that those gaps are real?
* Build an app that aggregates trust-weighted facility evidence across geography, such as state, city, district, or PIN code. Help planners distinguish real care gaps from data-poor regions.
* Minimum workflow: a planner selects a capability and geography, sees regional coverage, drills into the facility records behind an aggregate, and saves a planning scenario.

#### Track 3: Referral Copilot
* Question: Where should a patient or coordinator actually go?
* Build an app where a user enters a location and a care need, such as “dialysis near Jaipur” or “emergency surgery near Patna,” and receives an evidence-attached shortlist of candidate facilities.
* Minimum workflow: location and need in; ranked candidates out; each candidate shows distance, matching evidence, missing or suspicious evidence, and can be saved to a shortlist.

#### Track 4: Data Readiness Desk

* Question: What needs to be fixed before this dataset can be trusted for planning?
* Build an app for profiling, reviewing, and improving the facility dataset. Surface contradictions, suspicious claims, sparse fields, and high-leverage records for human review.
* Minimum workflow: show completeness and quality issues, provide a flagged-record review queue, and persist reviewer decisions for downstream use.

### Submission
Submit a Git repo and a live Databricks App. Be prepared to give a three-minute demo explaining the user, workflow, technical approach, and key tradeoffs.
