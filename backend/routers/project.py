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
