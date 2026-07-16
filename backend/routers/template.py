"""Template API routes."""
from fastapi import APIRouter, HTTPException
from services import template_service

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("")
def list_templates():
    return template_service.list_templates()


@router.get("/{template_id}")
def get_template(template_id: str):
    t = template_service.get_template(template_id)
    if not t:
        raise HTTPException(404, "模板不存在")
    return t


@router.post("")
def save_template(data: dict):
    return template_service.save_template(data)


@router.delete("/{template_id}")
def delete_template(template_id: str):
    ok = template_service.delete_template(template_id)
    if not ok:
        raise HTTPException(404, "模板不存在或不可删除")
    return {"ok": True}
