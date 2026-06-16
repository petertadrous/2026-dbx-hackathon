Databricks Apps & Agents for Good Hackathon 2026 — Comprehensive Overview
This document provides a highly detailed summary of the Databricks Apps & Agents for Good Hackathon 2026, hosted in partnership with OpenAI at the Data + AI Summit 2026 in San Francisco. It details the event parameters, core technical challenges, dataset characteristics, specific project tracks, and critical submission and judging criteria.
1. Event Overview & Key Parameters
The Databricks Apps & Agents for Good Hackathon 2026 is a multi-day competition focused on building powerful agentic data applications designed for social impact. The hackathon utilizes cutting-edge Databricks tooling including Lakebase, Agent Bricks, and Databricks Apps.
Parameter
Details
Dates
June 15 – June 16, 2026
Location
Marriott Marquis, San Francisco (In-person at Data + AI Summit 2026)
Eligibility
Accepted Data + AI Summit Attendees, above legal age of majority. Registration is closed.
Team Size
2 to 4 members per team (Applications via MLH)
Total Prize Pool
$17,500 in cash prizes
Submission Deadline
June 16, 2026 @ 2:30pm PDT


2. The Core Challenge
Participants are tasked with building a Databricks App to help non-technical healthcare planners, NGO coordinators, or analysts make high-stakes decisions using a messy, large-scale healthcare dataset. Applications must extract structured knowledge from unstructured claims, present clear evidence, systematically communicate uncertainty, and allow human-in-the-loop interventions (such as saving scenarios or overriding AI decisions).
3. Dataset Profiling
The hackathon provides a dataset consisting of 10,000 messy records of healthcare facilities across India, structured into 51 columns. While basic geographic features are highly complete (100% state/city coverage; 9,996 records with postcodes), the evidence fields capturing clinical capacity are noisy, self-reported, repetitive, and unevenly distributed. Teams must treat these fields as unverified claims rather than factual ground truth.
Field Name
Data Coverage
Description & Clinical Relevance
description
100.0%
Uneven free-text descriptions of claimed capabilities, procedures, and services.
capability
99.7%
Stated clinical offerings and operational competencies.
procedure
92.5%
Specific medical and surgical procedures claimed to be performed.
equipment
77.0%
Hardware, infrastructure, and diagnostic/therapeutic machinery available.
yearEstablished
47.8%
Temporal footprint of the facility to understand historical grounding.
numberDoctors
36.4%
Highly sparse staff count reflecting human resource limits.
capacity
25.2%
Bed counts or throughput capability; highly incomplete.


4. Core Technical Requirements
To qualify for judging, all sub-missions must meet the following architectural guidelines:
Runtime Environment: Must run reliably as a live Databricks App hosted on the Free Edition workspace.
Workflow Design: Tailored specifically for a non-technical end-user, featuring clear interaction paths.
Strict Citations: Every score, ranking, or capability claim must trace back via citation to the underlying source facility text or source URLs.
Uncertainty Mitigation: The app must actively flag weak or suspicious evidence instead of outputting hallucinated or absolute facts.
State Persistence: User actions—such as adding operational notes, overriding assessments, managing shortlists, or saving scenarios—must be persisted.
5. Available Hackathon Tracks
Teams must select and build their application for exactly one of the four official tracks:
Track 1: Facility Trust Desk
Core Question: Can this facility actually do what it claims?
Focuses on verifying specialized capabilities (e.g., ICU, maternity, emergency, oncology, trauma, NICU). Applications must generate structured trust signals (e.g., Strong Evidence, Partial Evidence, Weak/Suspicious Evidence, No Claim).
Minimum Workflow: Select capability and region → view ranked facilities → expand record to inspect precise citations → input human override with an operational note.
Track 2: Medical Desert Planner
Core Question: Where are the highest-risk gaps in care, and how confident are we that those gaps are real?
Focuses on aggregating trust-weighted infrastructure data across geographic dimensions (state, city, district, PIN code) to help planners differentiate actual care deserts from regions that are simply data-poor.
Minimum Workflow: Select clinical capability and geography → view aggregated regional coverage → drill down into the underlying facility records driving the aggregate → save the configuration to a planning scenario.
Track 3: Referral Copilot
Core Question: Where should a patient or coordinator actually go?
An optimization engine where users enter natural language care needs and locations (e.g., "dialysis near Jaipur") to receive trustworthy matching targets.
Minimum Workflow: Input location and clinical need → view ranked candidates with distance calculations → review matching vs. missing/suspicious evidence → persist selections to a saved shortlist.
Track 4: Data Readiness Desk
Core Question: What needs to be fixed before this dataset can be trusted for planning?
A data-quality and profiling application optimized for data cleansing. It surfaces logical contradictions, anomalies, extreme sparsity, and high-leverage records requiring immediate human review.
Minimum Workflow: View data completeness and systemic quality metrics → access a flagged-record review queue → execute and persist data cleaning/review decisions for downstream systems.
6. Submission Framework & Criteria
Submissions require a Git repository link, a project description, and a live, functional Databricks App. Teams must deliver a rigorous **three-minute live demo** covering user workflows, technical architecture, and engineering trade-offs.
Judging Evaluation Dimensions
Product Judgment: Clarity of user definition, design of the workflow, and thoughtfulness regarding system trade-offs.
Evidence and Uncertainty: Grounding of outputs in verifiable source text citations and honest, transparent handling of weak or conflicting data.
Technical Execution: Live reliability of the application and the technical depth of Databricks ecosystem integration (Lakebase, Agent Bricks, etc.).
Ambition: The degree to which the team extended functionality significantly beyond the specified minimum workflows.
7. Prize Distribution
1st Place: $10,000 cash prize (Gift Card format)
2nd Place: $5,000 cash prize (Gift Card format)
3rd Place: $2,500 cash prize (Gift Card format)
8. Event Timeline Checklist
May 31, 2026 (11:59pm PT): Applications Closed.
June 15, 2026 (8:00am – 4:00pm PT): Opening Ceremony (Marriott Marquis) & Hacking Begins.
June 16, 2026 (11:00am – 5:00pm PT): Hacker's Corner (Optional Mentor Collaboration Space).
June 16, 2026 (2:30pm PT): Project Submission Deadline.
June 16, 2026 (6:00pm – 9:00pm PT): Live Judging & Awards Ceremony.


