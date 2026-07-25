from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from agent_runtime.director_intake import build_project_intake, build_srt_intake, list_project_intakes, normalize_srt_intake, prompt_context
from agent_runtime.director_service import DirectorService

router = APIRouter(prefix="/api/director", tags=["director"])
service = DirectorService()


def _run_or_404(run_id: str):
    try:
        return service.get_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, {"code": "run_not_found", "message": f"Director run not found: {run_id}"}) from exc


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
