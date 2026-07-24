from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from services.script_structuring_service import (
    ScriptStructuringError,
    ScriptStructuringRequest,
    ScriptStructuringService,
)

router = APIRouter(prefix="/api/script-structuring", tags=["script-structuring"])


def _request_from_body(data: dict) -> ScriptStructuringRequest:
    duration = data.get("targetDurationSeconds")
    if duration is not None and (not isinstance(duration, int) or isinstance(duration, bool) or duration <= 0):
        raise ScriptStructuringError("targetDurationSeconds must be a positive integer")
    profile = data.get("profileSnapshot")
    if profile is not None and not isinstance(profile, dict):
        raise ScriptStructuringError("profileSnapshot must be an object")
    return ScriptStructuringRequest(
        source_text=data.get("sourceText"), title=str(data.get("title") or ""), topic=str(data.get("topic") or ""),
        target_duration_seconds=duration, profile_snapshot=profile,
    )


def _raise_contract_error(exc: ScriptStructuringError) -> None:
    raise HTTPException(503 if str(exc) == "script_structuring_provider_not_configured" else 422, str(exc)) from exc


@router.post("/normalize")
def normalize_agent_proposal(data: dict):
    """Validate an Agent proposal without calling a model or writing a project."""
    try:
        return ScriptStructuringService().normalize(_request_from_body(data), data.get("proposal"), provider_name=str(data.get("provider") or "external_agent"))
    except ScriptStructuringError as exc:
        _raise_contract_error(exc)


@router.post("/propose")
def propose_from_configured_provider(data: dict, request: Request):
    """Call an injected provider adapter; configuration lands in a later PR."""
    try:
        return ScriptStructuringService(getattr(request.app.state, "script_structuring_provider", None)).propose(_request_from_body(data))
    except ScriptStructuringError as exc:
        _raise_contract_error(exc)
