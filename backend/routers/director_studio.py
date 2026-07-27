"""Private Skill and Director Pack API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agent_runtime.director_studio import DirectorStudioRegistry, StudioValidationError

router = APIRouter(prefix="/api/director-studio", tags=["director-studio"])
registry = DirectorStudioRegistry()


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(404, {"code": str(exc), "message": "未找到请求的私有 Skill 或导演包。"})
    return HTTPException(422, {"code": "director_studio_invalid", "message": str(exc)})


@router.get("/capabilities")
def capabilities():
    return {"capabilities": registry.capabilities()}


@router.get("/skills")
def list_skills(includeDisabled: bool = True):
    return {"skills": registry.list_skills(include_disabled=includeDisabled)}


@router.post("/skills/import-gpt")
def import_gpt_skill(payload: dict):
    try:
        return {"skill": registry.import_gpt_draft(str(payload.get("text") or ""), name=payload.get("name"))}
    except (StudioValidationError, KeyError) as exc:
        raise _error(exc) from exc


@router.get("/skills/{skill_id}")
def get_skill(skill_id: str, version: int | None = None):
    try:
        return {"skill": registry.get_skill(skill_id, version)}
    except (StudioValidationError, KeyError) as exc:
        raise _error(exc) from exc


@router.put("/skills/{skill_id}")
def update_skill(skill_id: str, payload: dict):
    try:
        return {"skill": registry.update_skill(skill_id, payload)}
    except (StudioValidationError, KeyError) as exc:
        raise _error(exc) from exc


@router.post("/skills/{skill_id}/validate")
def validate_skill(skill_id: str, payload: dict | None = None):
    try:
        return registry.validate_skill(skill_id, (payload or {}).get("version"))
    except (StudioValidationError, KeyError) as exc:
        raise _error(exc) from exc


@router.post("/skills/{skill_id}/trial")
def trial_skill(skill_id: str, payload: dict | None = None):
    try:
        body = payload or {}
        subtitles = body.get("subtitles") if isinstance(body.get("subtitles"), list) else None
        return registry.trial_skill(skill_id, version=body.get("version"), subtitles=subtitles)
    except (StudioValidationError, KeyError) as exc:
        raise _error(exc) from exc


@router.post("/skills/{skill_id}/publish")
def publish_skill(skill_id: str):
    try:
        return {"skill": registry.publish_skill(skill_id)}
    except (StudioValidationError, KeyError) as exc:
        raise _error(exc) from exc


@router.post("/skills/{skill_id}/disable")
def disable_skill(skill_id: str):
    try:
        return {"skill": registry.set_skill_status(skill_id, "disabled")}
    except (StudioValidationError, KeyError) as exc:
        raise _error(exc) from exc


@router.post("/skills/{skill_id}/rollback")
def rollback_skill(skill_id: str, payload: dict):
    try:
        return {"skill": registry.rollback_skill(skill_id, int(payload.get("version")))}
    except (StudioValidationError, KeyError, TypeError, ValueError) as exc:
        raise _error(exc) from exc


@router.get("/packs")
def list_packs():
    return {"packs": registry.list_packs()}


@router.get("/packs/{pack_id}")
def get_pack(pack_id: str):
    try:
        return {"pack": registry.get_pack(pack_id)}
    except (StudioValidationError, KeyError) as exc:
        raise _error(exc) from exc


@router.post("/packs")
def save_pack(payload: dict):
    try:
        return {"pack": registry.save_pack(payload)}
    except (StudioValidationError, KeyError, TypeError, ValueError) as exc:
        raise _error(exc) from exc


@router.post("/packs/import")
def import_pack(payload: dict):
    try:
        document = payload.get("document") if isinstance(payload.get("document"), dict) else payload
        return {"pack": registry.import_pack(document)}
    except (StudioValidationError, KeyError, TypeError, ValueError) as exc:
        raise _error(exc) from exc


@router.get("/packs/{pack_id}/export")
def export_pack(pack_id: str):
    try:
        return registry.export_pack(pack_id)
    except (StudioValidationError, KeyError) as exc:
        raise _error(exc) from exc


@router.delete("/packs/{pack_id}")
def uninstall_pack(pack_id: str):
    try:
        registry.uninstall_pack(pack_id)
        return {"ok": True, "packId": pack_id}
    except (StudioValidationError, KeyError) as exc:
        raise _error(exc) from exc
