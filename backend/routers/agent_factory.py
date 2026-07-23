from fastapi import APIRouter, HTTPException
from services import agent_factory_service as factory
from services import template_batch_service as batches

router=APIRouter(prefix="/api/agent-factory",tags=["agent-factory"])

def _call(fn,*args):
    try: return fn(*args)
    except batches.BatchError as exc:
        status = 404 if exc.code in {"batch_not_found","item_not_found"} else 409 if exc.code in {"visual_coverage_incomplete","visual_plan_stale","item_not_ready_to_resume","project_changed","output_stale"} else 422
        raise HTTPException(status,{"code":exc.code,"message":str(exc)}) from exc

@router.get("/batches/{batch_id}/pending-visuals")
def pending(batch_id:str): return _call(factory.pending_visuals,batch_id)
@router.post("/batches/{batch_id}/items/{item_id}/visuals/import")
def import_visuals(batch_id:str,item_id:str,data:dict): return _call(factory.import_visuals,batch_id,item_id,data)
@router.post("/batches/{batch_id}/items/{item_id}/visuals/validate")
def validate_visuals(batch_id:str,item_id:str): return _call(factory.validate_visuals,batch_id,item_id)
@router.post("/batches/{batch_id}/items/{item_id}/resume")
def resume_item(batch_id:str,item_id:str): return _call(factory.resume_item,batch_id,item_id)
@router.post("/batches/{batch_id}/resume")
def resume_batch(batch_id:str): return _call(factory.resume_batch,batch_id)
@router.post("/batches/{batch_id}/continue")
def continue_factory(batch_id:str): return _call(factory.continue_factory,batch_id)
