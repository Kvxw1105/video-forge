from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agent_runtime.ai_image_settings import AIImageProviderSettings, load_ai_image_provider, public_ai_image_provider, save_ai_image_provider
from services.ai_image_service import approve_candidates, create_batch, fetch_models, get_batch, run_batch
from services.jobs import start_job

settings_router = APIRouter(prefix="/api/settings/ai-image", tags=["ai-image"])
router = APIRouter(prefix="/api/projects/{project_id}/ai-image", tags=["ai-image"])


@settings_router.get("")
def get_settings():
    return public_ai_image_provider(load_ai_image_provider())


@settings_router.put("")
def put_settings(payload: dict):
    current = load_ai_image_provider(); allowed = set(AIImageProviderSettings.model_fields)
    values = {key: value for key, value in payload.items() if key in allowed}
    if not str(values.get("apiKey") or "").strip(): values.pop("apiKey", None)
    settings = current.model_copy(update=values); save_ai_image_provider(settings)
    return public_ai_image_provider(settings)


@settings_router.post("/models")
def models(payload: dict | None = None):
    current = load_ai_image_provider(); values = dict(payload or {})
    if not str(values.get("apiKey") or "").strip(): values.pop("apiKey", None)
    return fetch_models(current.model_copy(update=values))


@settings_router.post("/test")
def test(payload: dict | None = None):
    return models(payload)


@router.post("/batches")
def start_batch(project_id: str, payload: dict):
    try:
        batch = create_batch(project_id, list(payload.get("items") or []), model=str(payload.get("model") or ""), size=str(payload.get("size") or "1024x1024"), candidate_count=max(1, min(4, int(payload.get("candidateCount") or 1))))
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    job = start_job("ai_image_batch", lambda update: run_batch(project_id, batch["batchId"], update))
    return {"batchId": batch["batchId"], "job": job, "batch": batch}


@router.get("/batches/{batch_id}")
def batch(project_id: str, batch_id: str):
    try: return get_batch(project_id, batch_id)
    except FileNotFoundError as exc: raise HTTPException(404, "batch_not_found") from exc


@router.post("/batches/{batch_id}/approve")
def approve(project_id: str, batch_id: str, payload: dict):
    try: return approve_candidates(project_id, batch_id, list(payload.get("selections") or []))
    except (FileNotFoundError, KeyError, ValueError) as exc: raise HTTPException(422, str(exc)) from exc
