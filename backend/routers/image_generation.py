from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from models.image_generation import ImageBatchCreateRequest
from services import image_generation_service as service
from services.jobs import start_job


settings_router = APIRouter(prefix="/api/settings/ai-image", tags=["ai-image"])
router = APIRouter(prefix="/api/projects/{project_id}/image-generation", tags=["ai-image"])


def _raise(error: service.ImageGenerationError):
    if error.code in {"project_not_found", "batch_not_found", "scene_not_found", "candidate_not_found"}:
        status = 404
    elif "stale" in error.code or error.code in {"channel_mismatch", "nothing_to_retry"}:
        status = 409
    else:
        status = 422
    raise HTTPException(status, {"code": error.code, "message": str(error)}) from error


@settings_router.get("")
def get_settings():
    return service.public_image_provider_settings(service.load_image_provider_settings())


@settings_router.put("")
def put_settings(payload: dict):
    try:
        return service.update_image_provider_settings(payload)
    except (service.ImageGenerationError, ValueError) as exc:
        if isinstance(exc, service.ImageGenerationError):
            _raise(exc)
        raise HTTPException(422, {"code": "settings_invalid", "message": str(exc)}) from exc


@settings_router.post("/test")
def test_settings(payload: dict | None = None):
    current = service.load_image_provider_settings()
    updates = {key: value for key, value in (payload or {}).items() if key in current.model_fields}
    if not str(updates.get("apiKey") or "").strip():
        updates.pop("apiKey", None)
    try:
        return service.fetch_image_provider_models(current.model_copy(update=updates))
    except service.ImageGenerationError as exc:
        _raise(exc)


@router.post("/batches")
def create(project_id: str, payload: ImageBatchCreateRequest):
    try:
        return service.create_batch(
            project_id,
            channel=payload.channel,
            provider_id=payload.providerId,
            model=payload.model,
            size=payload.size,
            candidate_count=payload.candidateCount,
            auto_approve=payload.autoApprove,
            style_anchor=payload.styleAnchor,
            continuity_anchor=payload.continuityAnchor,
            scene_ids=payload.sceneIds,
            scene_overrides=payload.sceneOverrides,
        )
    except service.ImageGenerationError as exc:
        _raise(exc)


@router.get("/batches/{batch_id}")
def get(project_id: str, batch_id: str):
    try:
        return service.get_batch(project_id, batch_id)
    except service.ImageGenerationError as exc:
        _raise(exc)


@router.get("/batches/{batch_id}/pending")
def pending(project_id: str, batch_id: str):
    try:
        batch = service.get_batch(project_id, batch_id)
        service.ensure_batch_current(batch)
        items = [item for item in batch["items"] if item["status"] in {"pending", "failed"}]
        return {
            "batchId": batch["batchId"],
            "projectId": batch["projectId"],
            "visualPlanId": batch["visualPlanId"],
            "visualSourceHash": batch["visualSourceHash"],
            "status": batch["status"],
            "items": items,
        }
    except service.ImageGenerationError as exc:
        _raise(exc)


@router.post("/batches/{batch_id}/run")
def run(project_id: str, batch_id: str):
    try:
        batch = service.get_batch(project_id, batch_id)
        service.ensure_batch_current(batch)
        if batch["channel"] not in {"builtin", "local"}:
            raise service.ImageGenerationError("channel_mismatch", "Only built-in or local visual batches can be run by Video Forge")
        runner = service.run_local_batch if batch["channel"] == "local" else service.run_builtin_batch
        job = start_job(
            "local_visual_generation" if batch["channel"] == "local" else "ai_image_generation",
            lambda update: runner(project_id, batch_id, update),
        )
        return {"batchId": batch_id, "job": job}
    except service.ImageGenerationError as exc:
        _raise(exc)


@router.post("/batches/{batch_id}/upload")
async def upload(
    project_id: str,
    batch_id: str,
    sceneId: str = Form(...),
    inputHash: str = Form(...),
    revisedPrompt: str = Form(""),
    file: UploadFile = File(...),
):
    try:
        return service.upload_agent_candidate(
            project_id,
            batch_id,
            sceneId,
            inputHash,
            await file.read(),
            revised_prompt=revisedPrompt,
        )
    except service.ImageGenerationError as exc:
        _raise(exc)


@router.post("/batches/{batch_id}/approve")
def approve(project_id: str, batch_id: str, payload: dict):
    try:
        return service.approve_candidates(project_id, batch_id, list(payload.get("selections") or []))
    except service.ImageGenerationError as exc:
        _raise(exc)


@router.post("/batches/{batch_id}/retry")
def retry(project_id: str, batch_id: str):
    try:
        return service.retry_failed_items(project_id, batch_id)
    except service.ImageGenerationError as exc:
        _raise(exc)
