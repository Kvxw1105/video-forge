"""Two-stage visual pause/resume orchestration over the durable batch manifest."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from pathlib import Path
import hashlib
import json

from services import template_batch_service as batches
from routers import visual_scene
from services.project_service import get_project
from shared.visual_scene import visual_source_hash

@dataclass(frozen=True)
class FactoryStageResult:
    outcome: Literal["continue", "awaiting_visual_assets"]
    patch: dict = field(default_factory=dict)

def factory_output_hash(project, variant_id: str, visual_plan, outputs) -> str:
    episode=project.structuredContent.episode
    payload={"variantId":variant_id,"canvas":project.canvas.model_dump(),"alignment":episode.alignment.generationId if episode.alignment else None,"plan":visual_plan.sourceHash,"scenes":[{"id":s.id,"assets":s.visualAssetIds,"primary":s.primaryAssetId} for s in visual_plan.scenes],"outputs":outputs.model_dump() if hasattr(outputs,"model_dump") else outputs,"jianyingPolicy":"create_new"}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def prepare_item_visual_stage(batch_id, spec, item, item_result: dict) -> FactoryStageResult:
    workflow = spec.visualWorkflow or {}
    if not workflow.get("enabled") or workflow.get("mode") != "generation_pack":
        return FactoryStageResult("continue")
    project = get_project(item_result.get("projectId"))
    if not project or not project.structuredContent or not project.subtitles:
        raise batches.BatchError("visual_timing_unavailable", "Structured subtitles are required before visual planning")
    episode=project.structuredContent.episode
    plan=episode.visualPlan
    if plan is None:
        proposal=visual_scene.propose(project.id,{"mode":workflow.get("planningMode","hybrid"),"unitsPerScene":workflow.get("unitsPerScene",3),"targetDuration":workflow.get("targetDuration",7),"minDuration":workflow.get("minDuration",4),"maxDuration":workflow.get("maxDuration",12)})
        saved=visual_scene.set_plan(project.id,{"plan":{"planId":f"visual_plan_{item.itemId}","sourceHash":proposal["sourceHash"],"scenes":proposal["scenes"],"settings":proposal["settings"]}})
        plan=project.structuredContent.episode.visualPlan if False else saved["plan"]
    errors=visual_scene.validate(project.id,{"plan":plan.model_dump() if hasattr(plan,"model_dump") else plan}).get("errors",[])
    if errors: raise batches.BatchError("visual_plan_stale", "; ".join(errors))
    pack=visual_scene.generation_pack(project.id)
    scenes=(plan.scenes if hasattr(plan,"scenes") else plan["scenes"])
    expected=[{"sceneId":s.id if hasattr(s,"id") else s["id"],"expectedFilename":f"scene_{i:03d}.png","requestedMediaType":s.requestedMediaType if hasattr(s,"requestedMediaType") else s.get("requestedMediaType","image")} for i,s in enumerate(scenes,1)]
    return FactoryStageResult("awaiting_visual_assets",{"visualPlanId":plan.planId if hasattr(plan,"planId") else plan["planId"],"generationPackPath":pack["path"],"expectedScenes":expected,"visualCoverage":{"totalScenes":len(expected),"boundScenes":0,"missingScenes":[s["sceneId"] for s in expected],"invalidScenes":[],"complete":False}})


def _item(batch_id: str, item_id: str):
    _, batch = batches._load(batch_id)
    for row in batch["items"]:
        if row["itemId"] == item_id:
            return batch, row
    raise batches.BatchError("item_not_found", f"Batch item not found: {item_id}")


def pending_visuals(batch_id: str) -> dict:
    _, batch = batches._load(batch_id); items=[]
    for row in batch["items"]:
        if row.get("status") != "awaiting_visual_assets": continue
        project = get_project(row.get("projectId"))
        plan = project.structuredContent.episode.visualPlan if project and project.structuredContent else None
        if not plan: continue
        items.append({"itemId":row["itemId"],"projectId":row["projectId"],"visualPlanId":plan.planId,"generationPackPath":row.get("generationPackPath"),"scenes":[{"sceneId":scene.id,"prompt":scene.prompt,"negativePrompt":scene.negativePrompt,"requestedMediaType":scene.requestedMediaType,"aspectRatio":project.canvas.ratio,"expectedFilename":f"scene_{index:03d}.png"} for index,scene in enumerate(plan.scenes,1)]})
    return {"batchId":batch_id,"status":batch.get("status"),"items":items}


def validate_visuals(batch_id: str, item_id: str) -> dict:
    batch,row=_item(batch_id,item_id); project=get_project(row.get("projectId"))
    if not project or not project.structuredContent: raise batches.BatchError("project_missing","Project is unavailable")
    plan=project.structuredContent.episode.visualPlan; scenes=list(plan.scenes) if plan else []
    bound=[scene for scene in scenes if scene.visualAssetIds]
    result={"complete":len(bound)==len(scenes),"totalScenes":len(scenes),"boundScenes":len(bound),"missingScenes":[scene.id for scene in scenes if not scene.visualAssetIds],"invalidScenes":[],"warnings":[]}
    result["validatedAt"] = batches._now()
    row.update({"status":"ready_to_resume" if result["complete"] else "awaiting_visual_assets","phase":"validating_visual_coverage" if result["complete"] else "awaiting_visual_assets","visualCoverage":result})
    batch["status"]="ready_to_resume" if result["complete"] else "awaiting_visual_assets"; batches._save(batch_id,batch)
    return result


def import_visuals(batch_id: str,item_id: str,data: dict) -> dict:
    batch,row=_item(batch_id,item_id)
    result=visual_scene.import_folder(row["projectId"],data)
    return {"imported":result["imported"],"coverage":validate_visuals(batch_id,item_id)}

def resume_item(batch_id: str, item_id: str) -> dict:
    batch,row=_item(batch_id,item_id)
    if row.get("status")=="succeeded":
        outputs=row.get("outputs") or {}
        preview=outputs.get("preview") or {}; jianying=outputs.get("jianying") or {}
        preview_path=str(preview.get("path") or "")
        draft_path=str(jianying.get("draftPath") or "")
        preview_ok=preview.get("status")=="succeeded" and (not preview_path or Path(preview_path).exists())
        draft_ok=jianying.get("status")=="succeeded" and (not draft_path or Path(draft_path).is_dir())
        if preview_ok and draft_ok:
            return {"status":"succeeded","reused":True}
        row["status"]="ready_to_resume"
    if not (row.get("visualCoverage") or {}).get("complete"): raise batches.BatchError("visual_coverage_incomplete","Visual coverage is incomplete")
    if row.get("status") not in {"ready_to_resume","failed"}: raise batches.BatchError("item_not_ready_to_resume","Item is not ready to resume")
    project=get_project(row.get("projectId"))
    if not project or not project.structuredContent: raise batches.BatchError("project_invalid","Structured project is invalid")
    plan=project.structuredContent.episode.visualPlan
    if not plan or plan.planId != row.get("visualPlanId") or plan.sourceHash != visual_source_hash(project.model_dump()): raise batches.BatchError("visual_plan_stale","Visual plan is stale")
    spec_payload,_=batches._load(batch_id); spec=batches.TemplateBatchSpec.model_validate(spec_payload)
    item=next(value for value in spec.items if value.itemId==item_id)
    output_hash=factory_output_hash(project,project.structuredContent.episode.activeVariantId or "publish",plan,item.outputs or spec.defaults.outputs)
    row.update({"status":"running","phase":"compiling_visuals"}); batches._save(batch_id,batch)
    try:
        batches._run_item_outputs(batch_id,item_id,row["projectId"],item.outputs or spec.defaults.outputs,row)
    except Exception as exc:
        row.update({"status":"failed","phase":row.get("phase") or "rendering_preview","errorCode":"output_failed","error":str(exc)[:500]})
        batch["status"]=batches._aggregate_batch_status(batch["items"]); batches._save(batch_id,batch)
        raise
    for output in (row.get("outputs") or {}).values():
        if isinstance(output,dict) and output.get("status")=="succeeded": output["inputHash"]=output_hash
    row.update({"status":"succeeded","phase":"done","finishedAt":batches._now()}); batch["status"]=batches._aggregate_batch_status(batch["items"]); batches._save(batch_id,batch)
    return {"status":"succeeded","reused":False}
