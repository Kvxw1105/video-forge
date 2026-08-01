from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from agent_runtime.director_intake import build_project_intake, build_srt_intake, list_project_intakes, normalize_srt_intake, prompt_context
from agent_runtime.director_service import DirectorService
from agent_runtime.director_studio import DirectorStudioRegistry, StudioValidationError

router = APIRouter(prefix="/api/director", tags=["director"])
service = DirectorService()
studio = DirectorStudioRegistry()


def _run_or_404(run_id: str):
    try:
        return service.get_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, {"code": "run_not_found", "message": f"Director run not found: {run_id}"}) from exc


def _visual_plan_scenes(intake: dict | None) -> list[dict]:
    """Use the established Project VisualScene IDs when a Director Run has a project."""
    structured = (intake or {}).get("structuredContent") if isinstance(intake, dict) else {}
    episode = structured.get("episode") if isinstance(structured, dict) else {}
    plan = episode.get("visualPlan") if isinstance(episode, dict) else {}
    scenes = plan.get("scenes") if isinstance(plan, dict) else []
    return [dict(scene) for scene in scenes if isinstance(scene, dict) and scene.get("id")]


@router.get("/intake/projects")
def list_intake_projects():
    """List projects that can be attached to a Director run."""
    return {"projects": list_project_intakes()}


@router.get("/intake/projects/{project_id}")
def inspect_project_intake(project_id: str):
    intake = build_project_intake(project_id)
    if intake is None:
        raise HTTPException(404, {"code": "project_not_found", "message": f"Project not found: {project_id}"})
    return {"intake": intake}


@router.post("/intake/srt")
async def upload_srt_intake(file: UploadFile = File(...)):
    """Parse an SRT upload without modifying a VideoForge project."""
    if not (file.filename or "").lower().endswith(".srt"):
        raise HTTPException(422, {"code": "srt_file_required", "message": "Please upload an .srt subtitle file."})
    try:
        intake = build_srt_intake(await file.read(), filename=file.filename)
    except ValueError as exc:
        raise HTTPException(422, {"code": "srt_invalid", "message": str(exc)}) from exc
    return {"intake": intake}


@router.post("/runs")
def create_run(payload: dict):
    payload = dict(payload)
    pack_context = None
    pack_id = str(payload.get("packId") or "").strip()
    if pack_id:
        try:
            pack_context = studio.resolve_pack(pack_id)
        except (StudioValidationError, KeyError) as exc:
            raise HTTPException(422, {"code": "director_pack_invalid", "message": str(exc)}) from exc
        payload["directorPack"] = pack_context["pack"]
        payload["skills"] = pack_context["skills"]
    intake = payload.get("intake")
    if intake is None and payload.get("projectId"):
        intake = build_project_intake(str(payload["projectId"]))
        if intake is None:
            raise HTTPException(404, {"code": "project_not_found", "message": f"Project not found: {payload['projectId']}"})
    if intake is not None:
        if payload.get("projectId"):
            # Project source is always re-read from VideoForge storage above.
            intake = build_project_intake(str(payload["projectId"]))
        else:
            try:
                intake = normalize_srt_intake(intake)
            except ValueError as exc:
                raise HTTPException(422, {"code": "intake_invalid", "message": str(exc)}) from exc
        payload["intake"] = intake
        task = str(payload.get("task") or "Create a structured, previewable video draft.").strip()
        payload["task"] = f"{task}\n\n{prompt_context(intake)}"
    if pack_context:
        if not payload.get("projectId"):
            raise HTTPException(422, {
                "code": "production_pack_project_required",
                "message": "Production Pack 需要选择已有 VideoForge 项目，才能把真实 Renderer 输出绑定到 Preview。",
                "recoverable": True,
            })
        timeline = intake.get("subtitleTimeline") if isinstance(intake, dict) and isinstance(intake.get("subtitleTimeline"), list) else []
        scene_plan = studio.build_scene_plan(timeline, pack_context["skills"], pack_context["pack"], visual_scenes=_visual_plan_scenes(intake))
        payload["scenePlan"] = scene_plan
        payload["productionPack"] = {"packId": pack_context["pack"]["packId"], "packVersion": pack_context["pack"]["version"], "packFingerprint": pack_context["pack"]["fingerprint"], "skillPins": pack_context["pack"]["skillPins"]}
        payload["task"] = f"{payload.get('task') or ''}\n\nDirector Pack (version-pinned, read-only):\n{json.dumps({'pack': pack_context['pack'], 'skills': [{'skillId': item['skillId'], 'version': item['version'], 'name': item['name'], 'directives': item['directives']} for item in pack_context['skills']], 'scenePlan': scene_plan}, ensure_ascii=False, separators=(',', ':'))}"
    try:
        run = service.create_run(payload)
    except ValueError as exc:
        raise HTTPException(422, {"code": "recipe_invalid", "message": str(exc)}) from exc
    if intake is not None:
        # DirectorStore intentionally has a compact create contract. Persist the
        # intake snapshot on the already-created Run without mutating its source project.
        run["intake"] = intake
        service.store.save(run)
    return run


@router.get("/runs")
def list_runs():
    return service.list_runs()


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    return _run_or_404(run_id)


@router.get("/runs/{run_id}/events")
def get_events(run_id: str, after: int = 0):
    _run_or_404(run_id)
    return {"runId": run_id, "events": service.events(run_id, after=after)}


@router.get("/runs/{run_id}/stream")
async def stream_events(run_id: str, request: Request, last_event_id: str | None = Header(default=None, alias="Last-Event-ID")):
    _run_or_404(run_id)
    start_after = int(last_event_id or 0)

    async def event_source():
        sent = start_after
        while True:
            if await request.is_disconnected():
                break
            rows = service.events(run_id, after=sent)
            for row in rows:
                sent = int(row["sequence"])
                yield f"id: {sent}\nevent: {row.get('type', 'message')}\ndata: {json.dumps(row, ensure_ascii=False)}\n\n"
            yield f": heartbeat {sent}\n\n"
            if rows and rows[-1].get("type") in {"run.completed", "run.cancelled"}:
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_source(), media_type="text/event-stream")


@router.post("/runs/{run_id}/messages")
def post_message(run_id: str, payload: dict):
    _run_or_404(run_id)
    return service.message(run_id, payload)


@router.post("/runs/{run_id}/approvals")
def approval(run_id: str, payload: dict):
    _run_or_404(run_id)
    try:
        return service.decide_approval(run_id, payload)
    except KeyError as exc:
        raise HTTPException(404, {"code": "approval_not_found", "message": "Approval was not found"}) from exc


@router.post("/runs/{run_id}/resume")
def resume(run_id: str):
    _run_or_404(run_id)
    return service.resume(run_id)


@router.post("/runs/{run_id}/cancel")
def cancel(run_id: str):
    _run_or_404(run_id)
    return service.cancel(run_id)


@router.get("/runs/{run_id}/artifacts")
def artifacts(run_id: str):
    _run_or_404(run_id)
    return service.artifacts(run_id)
