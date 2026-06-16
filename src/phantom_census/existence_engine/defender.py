"""Defender — rescue phantom verdicts on corroborating signals.

Max upgrade is `contested`. Cannot reach `real`.

Implements EE-DEF-001..005. Per E8 resolution, dataset-version reconciliation
(post-2022 district carve-outs, spelling drift) is OUT OF SCOPE for the
hackathon implementation and noted as a deferred LLD open question.
"""
from __future__ import annotations

import re

import pandas as pd

from .types import TestName, Verdict

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
MIN_DISTINCT_DOMAINS = 2

# Two-label suffixes that should NOT collapse to the second-level domain alone
# (e.g. co.uk, org.in). For the hackathon we keep this minimal.
_MULTI_LABEL_TLDS = {
    "co.uk", "co.in", "org.in", "gov.in", "ac.in", "edu.in",
    "co.jp", "ac.jp", "com.au",
}


def _registrable_domain(host: str) -> str:
    """Return eTLD+1 for a hostname. Strips subdomains; honors a small set of
    multi-label suffixes."""
    host = host.lower().strip(".")
    parts = host.split(".")
    if len(parts) < 2:
        return host
    last_two = ".".join(parts[-2:])
    last_three = ".".join(parts[-3:]) if len(parts) >= 3 else None
    if last_three and last_three.split(".", 1)[1] in _MULTI_LABEL_TLDS:
        return last_three
    return last_two


# @spec EE-DEF-003
def distinct_registrable_domains(text: object) -> int:
    if text is None:
        return 0
    s = str(text)
    if not s:
        return 0
    domains: set[str] = set()
    for url in URL_RE.findall(s):
        host = re.sub(r"^https?://", "", url, flags=re.IGNORECASE)
        host = host.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
        if host:
            domains.add(_registrable_domain(host))
    return len(domains)


def _norm(s: object) -> str:
    if s is None:
        return ""
    return str(s).strip().lower()


# @spec EE-DEF-002
def hfr_match(facility: pd.Series, hfr_df: pd.DataFrame) -> dict | None:
    if hfr_df.empty:
        return None
    fac_name = _norm(facility.get("facility_name"))
    fac_district = _norm(facility.get("district"))
    if not fac_name or not fac_district:
        return None
    for _, row in hfr_df.iterrows():
        if _norm(row.get("facility_name")) == fac_name and \
                _norm(row.get("district")) == fac_district:
            return row.to_dict()
    return None


# @spec EE-DEF-001..005
def run_defender(
    verdicts: pd.DataFrame,
    facilities: pd.DataFrame,
    hfr_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    updated = verdicts.copy()
    fac_by_id = facilities.set_index("facility_id")
    rescue_rows: list[dict] = []

    for idx, row in updated.iterrows():
        if row["verdict"] != Verdict.PHANTOM.value:
            continue
        fac_id = row["facility_id"]
        if fac_id not in fac_by_id.index:
            continue
        fac = fac_by_id.loc[fac_id]

        rescue_evidence: dict | None = None

        hfr = hfr_match(fac, hfr_df)
        if hfr is not None:
            rescue_evidence = {"signal": "hfr-match", "match": hfr}
        elif distinct_registrable_domains(fac.get("description")) >= MIN_DISTINCT_DOMAINS:
            rescue_evidence = {
                "signal": "multi-domain-urls",
                "domain_count": distinct_registrable_domains(fac.get("description")),
            }

        if rescue_evidence is not None:
            updated.at[idx, "verdict"] = Verdict.CONTESTED.value
            updated.at[idx, "reason"] = "defender-rescue"
            rescue_rows.append({
                "facility_id": fac_id,
                "test_name": TestName.DEFENDER_RESCUE.value,
                "result": "pass",
                "evidence_ref": rescue_evidence,
            })

    rescue_df = pd.DataFrame(rescue_rows, columns=[
        "facility_id", "test_name", "result", "evidence_ref",
    ])
    return updated, rescue_df
