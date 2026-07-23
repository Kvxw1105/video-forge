import shutil
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from services import agent_factory_service as factory
from services import template_batch_service as batches
from services.project_service import _project_dir

router=APIRouter(prefix="/api/agent-factory",tags=["agent-factory"])

def _call(fn,*args):
    try: return fn(*args)
    except batches.BatchError as exc:
        status = 404 if exc.code in {"batch_not_found","item_not_found","scene_not_found"} else 409 if exc.code in {"visual_coverage_incomplete","visual_plan_stale","item_not_ready_to_resume","project_changed","output_stale","asset_conflict"} else 422
        raise HTTPException(status,{"code":exc.code,"message":str(exc)}) from exc

@router.get("/batches/{batch_id}/pending-visuals")
def pending(batch_id:str): return _call(factory.pending_visuals,batch_id)
@router.post("/batches/{batch_id}/items/{item_id}/visuals/import")
def import_visuals(batch_id:str,item_id:str,data:dict): return _call(factory.import_visuals,batch_id,item_id,data)
@router.get("/batches/{batch_id}/items/{item_id}/visuals")
def get_item_visuals(batch_id:str,item_id:str): return _call(factory.item_visuals,batch_id,item_id)
@router.post("/batches/{batch_id}/items/{item_id}/visuals/upload")
async def upload_visual(batch_id: str, item_id: str, sceneId: str = Form(...), replace: bool = Form(False), file: UploadFile = File(...)):
    details = _call(factory.item_visuals, batch_id, item_id)
    scene = next((value for value in details["scenes"] if value["sceneId"] == sceneId), None)
    if not scene: raise HTTPException(404, {"code":"scene_not_found","message":"Scene was not found"})
    suffix = Path(str(file.filename or "")).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm"}:
        raise HTTPException(422, {"code":"asset_type_invalid","message":"Unsupported visual file type"})
    project_dir = _project_dir(details["projectId"])
    staging = project_dir / ".factory-upload-staging" / uuid4().hex
    staging.mkdir(parents=True)
    target = staging / f"{sceneId}{suffix}"
    size = 0
    try:
        with target.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 2 * 1024 * 1024 * 1024: raise HTTPException(413, {"code":"asset_too_large","message":"Visual file exceeds 2 GB"})
                handle.write(chunk)
        if size == 0: raise HTTPException(422, {"code":"asset_empty","message":"Visual file is empty"})
        result = _call(factory.import_visuals, batch_id, item_id, {"folder": str(staging), "replace": replace})
        return {"sceneId": sceneId, "size": size, **result}
    finally:
        shutil.rmtree(staging, ignore_errors=True)
@router.post("/batches/{batch_id}/items/{item_id}/visuals/unbind")
def unbind_visual(batch_id: str, item_id: str, data: dict): return _call(factory.unbind_visual, batch_id, item_id, str(data.get("sceneId") or ""), bool(data.get("deleteProjectAsset", False)))
@router.post("/batches/{batch_id}/items/{item_id}/visuals/validate")
def validate_visuals(batch_id:str,item_id:str): return _call(factory.validate_visuals,batch_id,item_id)
@router.post("/batches/{batch_id}/items/{item_id}/resume")
def resume_item(batch_id:str,item_id:str): return _call(factory.resume_item,batch_id,item_id)
@router.post("/batches/{batch_id}/resume")
def resume_batch(batch_id:str): return _call(factory.resume_batch,batch_id)
@router.post("/batches/{batch_id}/continue")
def continue_factory(batch_id:str): return _call(factory.continue_factory,batch_id)
