"""Defender Layer A — structured-field corroboration (post-Adjudicator).

Implements EE-LAYER-A-001..008.

Layer A runs after the Adjudicator. For each facility the Adjudicator marked
`phantom`, Layer A checks three deterministic rescue signals on data already
in Lakebase: URL mentions, HFR pre-cached snapshot match, and NFHS-5
named-staff overlap. When ≥1 signal fires, Layer A patches the final
`verdict` from `phantom` to `contested` and writes the signal trace to
`phantom_verdicts.rescue_applied` JSONB. The pre-rescue `adjudicator_verdict`
is preserved unchanged for audit (EE-ADJ-008).

Layer A NEVER writes to `facility_existence_tests`; the rescue trace lives
only in `phantom_verdicts.rescue_applied` (EE-LAYER-A-008).
"""
from __future__ import annotations

import re

import pandas as pd

from .types import Verdict


URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
MIN_DISTINCT_DOMAINS = 2
HFR_NAME_LEVENSHTEIN_MAX = 2

# A small multi-label suffix list so we don't collapse `.co.in` etc. to the TLD.
_MULTI_LABEL_TLDS = {
    "co.uk", "co.in", "org.in", "gov.in", "ac.in", "edu.in",
    "co.jp", "ac.jp", "com.au",
}


def _registrable_domain(host: str) -> str:
    host = host.lower().strip(".")
    parts = host.split(".")
    if len(parts) < 2:
        return host
    last_two = ".".join(parts[-2:])
    last_three = ".".join(parts[-3:]) if len(parts) >= 3 else None
    if last_three and last_three.split(".", 1)[1] in _MULTI_LABEL_TLDS:
        return last_three
    return last_two


def _norm(s: object) -> str:
    if s is None:
        return ""
    return str(s).strip().lower()


def _name_tokens(name: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", name.lower()) if t}


# @spec EE-LAYER-A-002
def _url_mentions_signal(facility: pd.Series) -> dict | None:
    desc = facility.get("description")
    # Defensive: when upstream passes a frame with duplicate facility_id rows,
    # `.loc[fac_id]` returns a DataFrame and `desc` is a Series — `not desc`
    # would raise. Coerce to scalar so the absent/empty check works either way.
    if isinstance(desc, pd.Series):
        desc = desc.dropna().astype(str).iloc[0] if not desc.dropna().empty else None
    if not desc:
        return None
    facility_tokens = _name_tokens(_norm(facility.get("facility_name")))
    distinct_domains: set[str] = set()
    matched_urls: list[str] = []
    for url in URL_RE.findall(str(desc)):
        host = re.sub(r"^https?://", "", url, flags=re.IGNORECASE)
        host = host.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
        if not host:
            continue
        domain = _registrable_domain(host)
        # EE-LAYER-A-002: self-published exclusion — when any facility-name
        # token appears as a substring of the registrable domain (e.g. facility
        # "Apollo Hospital" + domain "apollohospital.com"), treat the URL as
        # self-published and skip it.
        stop_words = {"hospital", "clinic", "centre", "center", "care",
                      "the", "and"}
        if facility_tokens and any(
            tok in domain for tok in facility_tokens
            if len(tok) >= 4 and tok not in stop_words
        ):
            continue
        if domain not in distinct_domains:
            distinct_domains.add(domain)
            matched_urls.append(url)
    if len(distinct_domains) >= MIN_DISTINCT_DOMAINS:
        return {
            "signal": "url-mentions",
            "domain_count": len(distinct_domains),
            "evidence_refs": sorted(matched_urls),
        }
    return None


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur[j] = min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[-1]


# @spec EE-LAYER-A-003
def _hfr_match_signal(facility: pd.Series, hfr_df: pd.DataFrame) -> dict | None:
    if hfr_df.empty:
        return None
    fac_name = _norm(facility.get("facility_name"))
    fac_district = _norm(facility.get("district"))
    if not fac_name or not fac_district:
        return None
    for _, row in hfr_df.iterrows():
        hfr_name = _norm(row.get("facility_name"))
        hfr_district = _norm(row.get("district"))
        if hfr_district != fac_district:
            continue
        if _levenshtein(fac_name, hfr_name) <= HFR_NAME_LEVENSHTEIN_MAX:
            return {
                "signal": "hfr-match",
                "matched_name": row.get("facility_name"),
                "evidence_refs": [str(row.to_dict())],
            }
    return None


# @spec EE-LAYER-A-004
def _nfhs_named_staff_signal(
    facility: pd.Series, nfhs_staff_df: pd.DataFrame,
) -> dict | None:
    if nfhs_staff_df.empty:
        return None
    desc = facility.get("description")
    if not desc:
        return None
    fac_district = _norm(facility.get("district"))
    if not fac_district:
        return None
    desc_n = _norm(desc)
    matched: list[str] = []
    for _, row in nfhs_staff_df.iterrows():
        if _norm(row.get("district")) != fac_district:
            continue
        name = _norm(row.get("staff_name"))
        if not name:
            continue
        if name in desc_n:
            matched.append(row.get("staff_name"))
    if matched:
        return {
            "signal": "nfhs-named-staff",
            "matched_staff": matched,
            "evidence_refs": matched,
        }
    return None


# @spec EE-LAYER-A-001, EE-LAYER-A-005, EE-LAYER-A-006, EE-LAYER-A-007,
# @spec EE-LAYER-A-008
def run_layer_a(
    verdicts: pd.DataFrame,
    facilities: pd.DataFrame,
    hfr_df: pd.DataFrame,
    nfhs_staff_df: pd.DataFrame,
) -> pd.DataFrame:
    """Patch phantom→contested when a rescue signal fires.

    Layer A reads `adjudicator_verdict`, patches `verdict` (not
    `adjudicator_verdict`), and writes `rescue_applied` JSONB. It does NOT
    write rows to `facility_existence_tests` (EE-LAYER-A-008).
    """
    out = verdicts.copy()
    if "rescue_applied" not in out.columns:
        out["rescue_applied"] = None
    fac_by_id = facilities.set_index("facility_id")

    for idx, row in out.iterrows():
        # EE-LAYER-A-001 — evaluate only facilities marked `phantom` by the
        # Adjudicator. `real` and `contested` are out of scope.
        if row["adjudicator_verdict"] != Verdict.PHANTOM.value:
            continue

        fac_id = row["facility_id"]
        if fac_id not in fac_by_id.index:
            continue
        fac = fac_by_id.loc[fac_id]

        signals: list[dict] = []
        urls = _url_mentions_signal(fac)
        if urls is not None:
            signals.append(urls)
        hfr = _hfr_match_signal(fac, hfr_df)
        if hfr is not None:
            signals.append(hfr)
        staff = _nfhs_named_staff_signal(fac, nfhs_staff_df)
        if staff is not None:
            signals.append(staff)

        if not signals:
            # EE-LAYER-A-007 — verdict + rescue unchanged.
            continue

        # EE-LAYER-A-005 — patch verdict to contested; preserve adjudicator_verdict.
        # EE-LAYER-A-006 — never upgrade to real.
        out.at[idx, "verdict"] = Verdict.CONTESTED.value
        out.at[idx, "rescue_applied"] = {
            "signals": signals,
            "evidence_refs": [r for s in signals for r in s.get("evidence_refs", [])],
        }

    return out
