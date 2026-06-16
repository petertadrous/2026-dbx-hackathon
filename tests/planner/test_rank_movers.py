"""Structural test for the top-movers panel.

@spec DS-RANK-002, DS-RANK-003
"""
from __future__ import annotations


def test_rank_movers_module_exposes_render():
    from phantom_census.planner_workspace.views import rank_movers
    assert callable(rank_movers.render)
    assert rank_movers.TOP_N == 5
