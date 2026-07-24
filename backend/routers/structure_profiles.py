"""HTTP API for reusable, versioned Structure Profiles."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from models.structure_profile import StructureProfile
from services import structure_profile_service
from services.project_service import get_project, update_project


router = APIRouter(prefix="/api", tags=["structure-profiles"])


def _profile_response(profile: StructureProfile) -> dict:
    return profile.model_dump()


@router.get("/structure-profiles")
def list_structure_profiles():
    return [_profile_response(profile) for profile in structure_profile_service.list_profiles()]


@router.get("/structure-profiles/{profile_id}")
def get_structure_profile(profile_id: str):
    profile = structure_profile_service.get_profile(profile_id)
    if profile is None:
        raise HTTPException(404, "structure profile not found")
    return _profile_response(profile)


@router.post("/structure-profiles", status_code=201)
def create_structure_profile(data: dict):
    try:
        return _profile_response(structure_profile_service.create_profile(data))
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.put("/structure-profiles/{profile_id}")
def update_structure_profile(profile_id: str, data: dict):
    try:
        profile = structure_profile_service.update_profile(profile_id, data)
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if profile is None:
        raise HTTPException(404, "structure profile not found")
    return _profile_response(profile)


@router.delete("/structure-profiles/{profile_id}")
def delete_structure_profile(profile_id: str):
    if structure_profile_service.get_profile(profile_id) is None:
        raise HTTPException(404, "structure profile not found")
    if not structure_profile_service.delete_profile(profile_id):
        raise HTTPException(403, "built-in structure profiles are read-only")
    return {"ok": True}


@router.post("/projects/{project_id}/structure-profile-snapshot")
def attach_structure_profile_snapshot(project_id: str, data: dict):
    profile_id = str(data.get("profileId") or "").strip()
    if not profile_id:
        raise HTTPException(422, "profileId is required")
    project = get_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    snapshot = structure_profile_service.profile_snapshot(profile_id)
    if snapshot is None:
        raise HTTPException(404, "structure profile not found")
    updated = update_project(project_id, {"structureProfileSnapshot": snapshot.model_dump()})
    return {
        "projectId": updated.id,
        "structureProfileSnapshot": updated.structureProfileSnapshot.model_dump(),
    }


@router.get("/projects/{project_id}/structure-profile-snapshot")
def get_structure_profile_snapshot(project_id: str):
    project = get_project(project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    if project.structureProfileSnapshot is None:
        raise HTTPException(404, "structure profile snapshot not found")
    return {
        "projectId": project.id,
        "structureProfileSnapshot": project.structureProfileSnapshot.model_dump(),
    }
