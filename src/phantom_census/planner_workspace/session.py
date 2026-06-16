"""Streamlit session state + planner identity resolution.

@spec PW-OVR-003, PW-SCEN-001, PW-SCEN-002
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

DEFAULT_CAPABILITY = "maternity"
LOCAL_DEV_PLANNER_ID = "local-dev"


def resolve_planner_id(request_headers: dict[str, str] | None = None) -> str:
    """Find the active planner identifier.

    Resolution order:
      1. Databricks Apps injects the authenticated user's email via the
         ``X-Forwarded-Email`` request header.
      2. The ``PLANNER_ID`` environment variable (set by Apps or local dev).
      3. The literal ``local-dev`` fallback.
    """
    headers = request_headers or {}
    via_header = headers.get("X-Forwarded-Email") or headers.get("x-forwarded-email")
    if via_header:
        return via_header
    env = os.environ.get("PLANNER_ID")
    if env:
        return env
    return LOCAL_DEV_PLANNER_ID


@dataclass
class WorkspaceState:
    capability: str = DEFAULT_CAPABILITY
    view: str = "raw"  # "raw" | "adjusted"
    selected_district: str | None = None
    last_error: str | None = None
    override_set: list[str] = field(default_factory=list)


def init_session_state(st_session: Any, planner_id: str) -> WorkspaceState:
    """Idempotently install workspace state onto ``st.session_state``."""
    if "workspace" not in st_session:
        st_session["workspace"] = WorkspaceState()
    if "planner_id" not in st_session:
        st_session["planner_id"] = planner_id
    return st_session["workspace"]
