"""Audit Queue ranking + inspector worksheet PDF.

@spec PW-AUDIT-001, PW-AUDIT-002, PW-AUDIT-003, PW-AUDIT-004, PW-AUDIT-005

LLM-free.
"""
from __future__ import annotations

import io

import pandas as pd

AUDIT_TOP_N = 50


# @spec PW-AUDIT-001, PW-AUDIT-002
def build_audit_queue(
    phantoms: pd.DataFrame,
    district_leverage: pd.DataFrame,
) -> pd.DataFrame:
    """Rank phantom-verdicted facilities by district leverage.

    leverage = burden_weight × verified_facility_count × phantom_density
              (phantom_density = phantom_count / area_km2)

    Ties broken by the number of failed tests in `test_outcome_vector`
    (more fails → higher rank).

    `phantoms` may contain non-phantom rows (e.g., from a wider read); they
    are filtered out unless the `verdict` column is absent (in which case
    every row is assumed to be phantom — fixture compatibility).
    """
    df = phantoms.copy()
    if "verdict" in df.columns:
        # Rows without an explicit verdict are assumed phantom-filtered upstream
        # (the audit-view SQL already restricts to verdict='phantom'); only
        # rows that explicitly disagree are dropped.
        df = df[df["verdict"].fillna("phantom") == "phantom"]
    if df.empty:
        return _empty_queue_frame()

    leverage_per_district = _leverage_table(district_leverage)
    df = df.merge(leverage_per_district, on="district_id", how="left")
    df["leverage"] = df["leverage"].fillna(0.0)
    df["failed_tests_count"] = df["test_outcome_vector"].apply(_count_failed)
    df["failed_tests"] = df["test_outcome_vector"].apply(_failed_test_names)

    df = df.sort_values(
        by=["leverage", "failed_tests_count"],
        ascending=[False, False],
        kind="mergesort",
    ).head(AUDIT_TOP_N).reset_index(drop=True)

    df["rank"] = df.index + 1
    cols = ["rank", "facility_id", "facility_name", "district_name",
            "pincode", "latitude", "longitude", "failed_tests"]
    return df[cols]


def _empty_queue_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "rank", "facility_id", "facility_name", "district_name",
        "pincode", "latitude", "longitude", "failed_tests",
    ])


def _leverage_table(district_leverage: pd.DataFrame) -> pd.DataFrame:
    df = district_leverage.copy()
    area = df["area_km2"].replace(0, 1.0)
    df["leverage"] = (
        df["burden_weight"]
        * df["verified_facility_count"].clip(lower=1)
        * (df["phantom_count"] / area)
    )
    return df[["district_id", "leverage"]]


def _count_failed(tov: object) -> int:
    if not isinstance(tov, list):
        return 0
    return sum(1 for o in tov if isinstance(o, dict) and o.get("result") == "fail")


def _failed_test_names(tov: object) -> str:
    if not isinstance(tov, list):
        return ""
    names = [o.get("test_name") for o in tov
             if isinstance(o, dict) and o.get("result") == "fail"]
    return ", ".join(n for n in names if n)


# @spec PW-AUDIT-003
def render_inspector_worksheet_pdf(queue: pd.DataFrame) -> bytes:
    """Render the inspector worksheet PDF in-process via reportlab.

    One row per facility; columns: rank, facility, district, PIN, GPS, and a
    checkbox list of failed tests so the inspector can mark physical
    verification on the ground. No external service calls.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph,
        Spacer,
    )
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()

    flow = [
        Paragraph("Phantom Census — Inspector Worksheet", styles["Title"]),
        Paragraph(
            "Top-50 facilities to audit, ordered by leverage. "
            "Check each row after physical verification.",
            styles["BodyText"],
        ),
        Spacer(1, 0.2 * inch),
    ]

    data = [["#", "Facility", "District", "PIN", "GPS", "Failed tests", "Verified"]]
    for _, r in queue.iterrows():
        gps = f"{r.get('latitude', '')},{r.get('longitude', '')}"
        data.append([
            r["rank"], r["facility_name"], r["district_name"],
            r.get("pincode", ""), gps, r.get("failed_tests", ""), "☐",
        ])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    flow.append(table)

    doc.build(flow)
    return buf.getvalue()
