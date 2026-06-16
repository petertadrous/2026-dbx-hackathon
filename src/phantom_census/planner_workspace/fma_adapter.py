"""Foundation Model API adapter for the AI Evidence Layer + Genie sidebar.

The AI Evidence Layer (`existence_engine.ai_evidence_layer.maybe_render`) and
the Genie sidebar both accept an injectable callable. This module provides:

* `build_ai_evidence_adapter()` — returns the callable to pass as `ai_query`
  for `maybe_render`. Resolves an environment-configured Databricks
  Foundation Model API client at first call; if unconfigured, returns a
  callable that raises so the existence-engine's template-fallback path
  (EE-AI-009) fires.

* `build_genie_sql_adapter()` — returns the callable Genie's sidebar uses to
  translate a natural-language question to SQL. Same env-var contract.

Env vars:
    DATABRICKS_HOST   — workspace URL, e.g. `https://your-ws.cloud.databricks.com`
    DATABRICKS_TOKEN  — PAT or service-principal token
    FMA_MODEL         — model serving endpoint name; default `databricks-meta-llama-3-1-70b-instruct`

When `DATABRICKS_HOST` or `DATABRICKS_TOKEN` is missing, both adapters
degrade to a default that raises `RuntimeError("FMA not configured")`. The
verdict path treats this exactly the same as an FMA error: template
fallback fires, the planner sees a `(template fallback)` marker on the AI
Advisory block.

The `token_usage: 0` claim on the deterministic verdict path is unchanged by
this module — adapters are wired in by the planner workspace at session
start; the existence-engine batch pipeline never sees them.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable

_DEFAULT_MODEL = "databricks-meta-llama-3-1-70b-instruct"


class FMANotConfiguredError(RuntimeError):
    """Raised by the default adapter when Databricks env vars are missing.

    The AI Evidence Layer's exception path (EE-AI-009) catches any Exception
    and emits a template-fallback payload, so callers do not need to special-
    case this — but the explicit class makes test assertions clearer.
    """


def _env_configured() -> bool:
    return bool(os.environ.get("DATABRICKS_HOST")) and bool(
        os.environ.get("DATABRICKS_TOKEN")
    )


def build_ai_evidence_adapter() -> Callable[..., dict[str, Any]]:
    """Return the `ai_query` callable for `ai_evidence_layer.maybe_render`.

    Production adapter shape (when env vars are set):
        adapter(facility_id=..., test_outcome_vector=...,
                adjudicator_verdict=..., rescue_applied=...,
                layer_c_synthesis=...) -> dict matching EE-AI-008 shape

    The default (env vars unset) raises `FMANotConfiguredError`; the AI
    Evidence Layer's broad `except Exception` (EE-AI-009) lands on the
    template fallback.
    """
    if not _env_configured():
        return _raising_evidence_adapter

    # Lazy-import so unit tests don't pay the import cost when the adapter
    # is never actually called.
    def _evidence_adapter(**kwargs: Any) -> dict[str, Any]:
        return _call_serving_endpoint(
            model=os.environ.get("FMA_MODEL", _DEFAULT_MODEL),
            prompt=_evidence_prompt(kwargs),
            response_shape=_EVIDENCE_RESPONSE_SHAPE,
        )

    return _evidence_adapter


def build_genie_sql_adapter() -> Callable[[str], str]:
    """Return the NL-question → SQL callable for the Genie sidebar.

    Production adapter shape:
        adapter(question: str) -> str (SQL query)

    Default raises `FMANotConfiguredError`; the Genie sidebar catches and
    displays "endpoint not configured" instead.
    """
    if not _env_configured():
        return _raising_genie_adapter

    def _genie_adapter(question: str) -> str:
        sql = _call_serving_endpoint(
            model=os.environ.get("FMA_MODEL", _DEFAULT_MODEL),
            prompt=_genie_prompt(question),
            response_shape=_GENIE_RESPONSE_SHAPE,
        )
        return sql.get("sql", "") if isinstance(sql, dict) else str(sql)

    return _genie_adapter


# ─── private prompt + response helpers ───────────────────────────────────


_EVIDENCE_RESPONSE_SHAPE = {
    "recommendation": "force-real | force-phantom | evidence-too-thin",
    "confidence": "low | medium | high",
    "reasoning": "one paragraph",
    "cited_evidence_rows": "list of row ids",
    "source": "fma",
}


_GENIE_RESPONSE_SHAPE = {
    "sql": "SELECT … FROM operational.… (read-only, schema-qualified)",
}


def _evidence_prompt(payload: dict[str, Any]) -> str:
    return (
        "You are reviewing a healthcare facility flagged as `contested` by a "
        "deterministic Adjudicator. Weigh the test outcome vector + Layer A/B/C "
        "evidence and emit JSON matching this shape: "
        f"{json.dumps(_EVIDENCE_RESPONSE_SHAPE)}\n\n"
        "Payload:\n" + json.dumps(payload, default=str, indent=2)
    )


def _genie_prompt(question: str) -> str:
    return (
        "Translate the following natural-language question to a read-only "
        "schema-qualified SQL query against the Phantom Census Lakebase. "
        "Allowed tables: operational.desert_scores, operational.phantom_verdicts, "
        "operational.facility_existence_tests, team.budget_allocations, "
        "team.planner_overrides, vf_facilities. Emit JSON: "
        f"{json.dumps(_GENIE_RESPONSE_SHAPE)}\n\n"
        f"Question: {question}"
    )


def _call_serving_endpoint(
    *, model: str, prompt: str, response_shape: dict[str, str],
) -> dict[str, Any]:
    """Hit a Databricks Model Serving endpoint.

    Kept in a function so tests can monkeypatch a fake HTTP client. The
    implementation is intentionally minimal — the production path goes
    through the Databricks SDK + `ai_query` SQL function when running inside
    a Databricks notebook, but the workspace runs as a standalone Streamlit
    app and needs the HTTPS path.
    """
    import requests

    host = os.environ["DATABRICKS_HOST"].rstrip("/")
    token = os.environ["DATABRICKS_TOKEN"]
    url = f"{host}/serving-endpoints/{model}/invocations"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "messages": [
            {"role": "system",
             "content": "You return JSON matching the requested schema. "
                        "No prose; no markdown fences."},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    resp = requests.post(url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    content = (
        data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    )
    parsed = json.loads(content) if isinstance(content, str) else content
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _raising_evidence_adapter(**_kwargs: Any) -> dict[str, Any]:
    raise FMANotConfiguredError(
        "FMA adapter not configured; set DATABRICKS_HOST + DATABRICKS_TOKEN"
    )


def _raising_genie_adapter(_question: str) -> str:
    raise FMANotConfiguredError(
        "Genie adapter not configured; set DATABRICKS_HOST + DATABRICKS_TOKEN"
    )
