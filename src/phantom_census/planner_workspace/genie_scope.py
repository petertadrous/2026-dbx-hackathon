"""Genie sidebar SQL allow-list — PW-GENIE-001..003.

Explicit allowlist of tables Genie may SELECT from. Write-statement detection
is conservative: SQL containing INSERT/UPDATE/DELETE/DROP/ALTER/MERGE/TRUNCATE
keywords (case-insensitive) is denied regardless of which table appears.
"""
from __future__ import annotations

import re


# @spec PW-GENIE-001
GENIE_ALLOWED_TABLES = frozenset({
    "operational.desert_scores",
    "operational.phantom_verdicts",
    "operational.facility_existence_tests",
    "team.budget_allocations",
    "team.planner_overrides",
    "vf_facilities",
})


# @spec PW-GENIE-002
GENIE_DENIED_TABLES = frozenset({
    "cache.claim_minhash",
    "cache.description_embeddings",
    "team.saved_scenarios",
})


_WRITE_KEYWORDS_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|MERGE|TRUNCATE|CREATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)
_TABLE_REF_RE = re.compile(
    r"\bFROM\s+([a-zA-Z_]\w*\.[a-zA-Z_]\w*|[a-zA-Z_]\w*)|"
    r"\bJOIN\s+([a-zA-Z_]\w*\.[a-zA-Z_]\w*|[a-zA-Z_]\w*)",
    re.IGNORECASE,
)


# @spec PW-GENIE-003
def is_genie_sql_allowed(sql: str) -> bool:
    """Return True only if the SQL is a SELECT against tables in the allowlist.

    The check is conservative — write keywords are denied across the board,
    and any referenced table not in `GENIE_ALLOWED_TABLES` denies the query.
    Genie unqualified `vf_facilities` is allowed; everything else must use a
    schema-qualified name.
    """
    if _WRITE_KEYWORDS_RE.search(sql):
        return False
    referenced: set[str] = set()
    for match in _TABLE_REF_RE.finditer(sql):
        name = match.group(1) or match.group(2)
        if name:
            referenced.add(name.lower())
    if not referenced:
        return False
    if any(t in GENIE_DENIED_TABLES for t in referenced):
        return False
    return all(t in GENIE_ALLOWED_TABLES for t in referenced)
