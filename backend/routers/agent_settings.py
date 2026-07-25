from __future__ import annotations

import time
from urllib.parse import urlparse
import httpx
from fastapi import APIRouter, HTTPException
from agent_runtime.provider_settings import AgentProviderSettings, load_agent_provider, public_agent_provider, save_agent_provider

router = APIRouter(prefix="/api/settings/agent", tags=["agent-settings"])


def _models_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Base URL must be a complete http(s) URL")
    return base if base.endswith("/models") else f"{base}/models"


def _headers(settings: AgentProviderSettings) -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.apiKey}"} if settings.apiKey else {}


@router.get("")
def get_agent_settings():
    return public_agent_provider(load_agent_provider())


@router.put("")
def put_agent_settings(payload: dict):
    current = load_agent_provider()
    allowed = set(AgentProviderSettings.model_fields)
    updates = {key: value for key, value in payload.items() if key in allowed}
    if not str(updates.get("apiKey") or "").strip():
        updates.pop("apiKey", None)
    try:
        updated = current.model_copy(update=updates)
        if updated.baseUrl:
            _models_url(updated.baseUrl)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    save_agent_provider(updated)
    return public_agent_provider(updated)


@router.post("/models")
def fetch_models(payload: dict | None = None):
    updates = dict(payload or {})
    if not str(updates.get("apiKey") or "").strip():
        updates.pop("apiKey", None)
    settings = load_agent_provider().model_copy(update=updates)
    try:
        url = _models_url(settings.baseUrl)
        started = time.monotonic()
        response = httpx.get(url, headers=_headers(settings), timeout=settings.timeoutSeconds)
        latency = round((time.monotonic() - started) * 1000)
        if response.status_code >= 400:
            return {"ok": False, "latencyMs": latency, "message": f"HTTP {response.status_code}: {response.text[:180]}", "models": []}
        raw = response.json()
        rows = raw.get("data", raw.get("models", raw if isinstance(raw, list) else []))
        models = [{"id": str(row.get("id") or row.get("name")), "name": str(row.get("name") or row.get("id"))} for row in rows if isinstance(row, dict) and (row.get("id") or row.get("name"))]
        return {"ok": True, "latencyMs": latency, "models": models, "message": f"Connected: {len(models)} models"}
    except (httpx.HTTPError, ValueError) as exc:
        return {"ok": False, "latencyMs": None, "models": [], "message": str(exc)}


@router.post("/test")
def test_connection(payload: dict | None = None):
    return fetch_models(payload)
