"""Tests for PW-GENIE-001..003 — Genie SQL allow-list."""
from __future__ import annotations

import pytest

from phantom_census.planner_workspace.genie_scope import (
    GENIE_ALLOWED_TABLES,
    GENIE_DENIED_TABLES,
    is_genie_sql_allowed,
)


# @spec PW-GENIE-001
def test_allowlist_includes_required_tables():
    expected = {
        "operational.desert_scores",
        "operational.phantom_verdicts",
        "operational.facility_existence_tests",
        "team.budget_allocations",
        "team.planner_overrides",
        "vf_facilities",
    }
    assert expected <= set(GENIE_ALLOWED_TABLES)


# @spec PW-GENIE-002
def test_denylist_excludes_minhash_embeddings_scenarios():
    denied = {
        "cache.claim_minhash",
        "cache.description_embeddings",
        "team.saved_scenarios",
    }
    assert denied <= set(GENIE_DENIED_TABLES)


# @spec PW-GENIE-003
def test_select_is_allowed_on_allowed_table():
    assert is_genie_sql_allowed("SELECT * FROM operational.desert_scores")
    assert is_genie_sql_allowed("SELECT district_id FROM operational.phantom_verdicts WHERE verdict='phantom'")


# @spec PW-GENIE-003
def test_select_is_denied_on_denied_table():
    assert not is_genie_sql_allowed("SELECT * FROM cache.claim_minhash")
    assert not is_genie_sql_allowed("SELECT * FROM team.saved_scenarios")


# @spec PW-GENIE-003
def test_write_statements_are_denied():
    assert not is_genie_sql_allowed("INSERT INTO operational.desert_scores VALUES (1)")
    assert not is_genie_sql_allowed("UPDATE operational.phantom_verdicts SET verdict='real'")
    assert not is_genie_sql_allowed("DELETE FROM team.planner_overrides")
    assert not is_genie_sql_allowed("DROP TABLE operational.phantom_verdicts")
