from fastapi import APIRouter, HTTPException
from services.project_service import (
    ProjectLoadError,
    create_project,
    delete_project,
    get_project,
    list_deleted_projects,
    list_projects,
    restore_project,
    update_project,
)
from shared.structured_content import compile_structured_variant


router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("")
def create(data: dict):
    try:
        p = create_project(
            data.get("name", "未命名"),
            data.get("canvas_ratio", "9:16"),
            data.get("template_id"),
        )
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return p.model_dump()


@router.get("")
def list_all():
    return list_projects()


@router.get("/trash/items")
def list_trash():
    return list_deleted_projects()


@router.post("/trash/{trash_id}/restore")
def restore(trash_id: str):
    try:
        project = restore_project(trash_id)
    except FileExistsError as e:
        raise HTTPException(409, "A project with the same ID already exists") from e
    if not project:
        raise HTTPException(404, "Deleted project not found")
    return project.model_dump()


@router.get("/{project_id}")
def get_one(project_id: str):
    try:
        p = get_project(project_id)
    except ProjectLoadError as e:
        raise HTTPException(500, str(e)) from e
    if not p:
        raise HTTPException(404, "项目不存在")
    return p.model_dump()


@router.get("/{project_id}/structured/variants/{variant_id}/compile")
def compile_variant(project_id: str, variant_id: str):
    try:
        p = get_project(project_id)
    except ProjectLoadError as e:
        raise HTTPException(500, str(e)) from e
    if not p:
        raise HTTPException(404, "Project not found")
    if p.structuredContent is None:
        raise HTTPException(409, "Project does not contain structuredContent")
    try:
        compiled = compile_structured_variant(p, variant_id)
    except KeyError as e:
        raise HTTPException(404, f"Variant not found: {variant_id}") from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {
        "episodeId": compiled.episode_id,
        "variantId": compiled.variant_id,
        "variantName": compiled.variant_name,
        "blockIds": list(compiled.block_ids),
        "blockCount": len(compiled.blocks),
        "script": compiled.script,
        "warnings": list(compiled.warnings),
    }


@router.put("/{project_id}")
def update(project_id: str, data: dict):
    try:
        p = update_project(project_id, data)
    except ProjectLoadError as e:
        raise HTTPException(500, str(e)) from e
    if not p:
        raise HTTPException(404, "项目不存在")
    return p.model_dump()


@router.delete("/{project_id}")
def delete(project_id: str):
    trash_item = delete_project(project_id)
    if not trash_item:
        raise HTTPException(404, "项目不存在")
    return {"ok": True, "trashItem": trash_item}
