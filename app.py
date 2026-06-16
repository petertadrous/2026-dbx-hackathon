"""Phantom Census Streamlit app entry.

Launch::

    LAKEBASE_URL=postgresql+psycopg://... streamlit run app.py
"""
from __future__ import annotations

from phantom_census.planner_workspace import main

main()
