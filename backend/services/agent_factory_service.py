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
from services.project_service import _project_dir, update_project
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
    if not plan or plan.sourceHash != visual_source_hash(project.model_dump()):
        raise batches.BatchError("visual_plan_stale", "Visual plan is stale")
    bound=[scene for scene in scenes if scene.visualAssetIds]
    result={"complete":len(bound)==len(scenes),"totalScenes":len(scenes),"boundScenes":len(bound),"missingScenes":[scene.id for scene in scenes if not scene.visualAssetIds],"invalidScenes":[],"warnings":[]}
    result["validatedAt"] = batches._now()
    state = row.get("status") if row.get("status") == "succeeded" and result["complete"] else "ready_to_resume" if result["complete"] else "awaiting_visual_assets"
    phase = row.get("phase") if state == "succeeded" else "validating_visual_coverage" if result["complete"] else "awaiting_visual_assets"
    row.update({"status":state,"phase":phase,"visualCoverage":result})
    batch["status"] = batches._aggregate_batch_status(batch["items"]); batches._save(batch_id,batch)
    return result


def import_visuals(batch_id: str,item_id: str,data: dict) -> dict:
    batch,row=_item(batch_id,item_id)
    result=visual_scene.import_folder(row["projectId"],data)
    return {"imported":result["imported"],"coverage":validate_visuals(batch_id,item_id)}


def item_visuals(batch_id: str, item_id: str) -> dict:
    """Return the Visual Plan as a user-facing, timestamp-authoritative view."""
    _, row = _item(batch_id, item_id)
    project = get_project(row.get("projectId"))
    if not project or not project.structuredContent:
        raise batches.BatchError("project_invalid", "Structured project is invalid")
    episode = project.structuredContent.episode
    plan = episode.visualPlan
    if not plan:
        raise batches.BatchError("visual_plan_missing", "Visual plan is unavailable")
    if plan.sourceHash != visual_source_hash(project.model_dump()):
        raise batches.BatchError("visual_plan_stale", "Visual plan is stale")
    subtitles = {item.id: item for item in project.subtitles}
    bindings = {item.blockId: item for item in episode.bindings}
    assets = {item.id: item for item in project.assets}
    audio_path = str(episode.alignment.audioPath if episode.alignment else "")
    audio_duration = next((float(item.duration or 0) for item in project.audio.voiceovers if item.id == (episode.alignment.voiceoverId if episode.alignment else "")), 0.0)
    scenes = []
    for index, scene in enumerate(plan.scenes, 1):
        ids = list(scene.subtitleIds)
        selected = [subtitles[value] for value in ids if value in subtitles]
        start = float(selected[0].start) if selected else 0.0
        end = float(selected[-1].end) if selected else start
        asset = assets.get(scene.primaryAssetId or "")
        binding = bindings.get(scene.blockId)
        scenes.append({
            "sceneId": scene.id, "sceneIndex": index, "blockId": scene.blockId,
            "subtitleIds": ids, "start": start, "end": end, "duration": end - start,
            "text": "".join(item.text for item in selected), "summary": scene.summary,
            "prompt": scene.prompt, "negativePrompt": scene.negativePrompt,
            "requestedMediaType": scene.requestedMediaType, "aspectRatio": project.canvas.ratio,
            "expectedFilename": f"scene_{index:03d}.png",
            "audioStart": float(binding.audioSlice.sourceStart) if binding and binding.audioSlice else start,
            "audioEnd": float(binding.audioSlice.sourceEnd) if binding and binding.audioSlice else end,
            "boundAsset": None if not asset else {"assetId": asset.id, "name": asset.name, "type": asset.type, "path": asset.path, "size": (_project_dir(project.id) / asset.path).stat().st_size if (_project_dir(project.id) / asset.path).is_file() else 0},
            "coverageStatus": "bound" if asset else "missing",
        })
    return {"batchId": batch_id, "itemId": item_id, "projectId": project.id, "itemName": project.name, "status": row.get("status"), "visualPlanId": plan.planId, "sourceHash": plan.sourceHash, "audio": {"url": f"/api/projects/{project.id}/assets/stream?path={audio_path}" if audio_path else "", "duration": audio_duration}, "coverage": row.get("visualCoverage") or {"totalScenes": len(scenes), "boundScenes": sum(bool(item["boundAsset"]) for item in scenes), "missingScenes": [item["sceneId"] for item in scenes if not item["boundAsset"]], "complete": all(item["boundAsset"] for item in scenes)}, "scenes": scenes}


def unbind_visual(batch_id: str, item_id: str, scene_id: str, delete_project_asset: bool = False) -> dict:
    _, row = _item(batch_id, item_id)
    project = get_project(row.get("projectId"))
    if not project or not project.structuredContent:
        raise batches.BatchError("project_invalid", "Structured project is invalid")
    plan = project.structuredContent.episode.visualPlan
    if not plan or plan.sourceHash != visual_source_hash(project.model_dump()):
        raise batches.BatchError("visual_plan_stale", "Visual plan is stale")
    target = next((scene for scene in plan.scenes if scene.id == scene_id), None)
    if not target:
        raise batches.BatchError("scene_not_found", f"Scene not found: {scene_id}")
    asset_ids = set(target.visualAssetIds)
    plan_data = plan.model_dump()
    for scene in plan_data["scenes"]:
        if scene["id"] == scene_id:
            scene["visualAssetIds"] = []; scene["primaryAssetId"] = None
    assets = list(project.assets)
    warnings = []
    if delete_project_asset and asset_ids:
        used_elsewhere = {value for scene in plan.scenes if scene.id != scene_id for value in scene.visualAssetIds}
        removable = asset_ids - used_elsewhere
        if asset_ids - removable:
            warnings.append("asset is still referenced by another scene; file was retained")
        assets = [asset for asset in assets if asset.id not in removable]
        for asset in project.assets:
            if asset.id in removable:
                path = _project_dir(project.id) / asset.path
                if path.is_file(): path.unlink()
    update_project(project.id, {"assets": [asset.model_dump() if hasattr(asset, "model_dump") else asset for asset in assets], "structuredContent": {**project.structuredContent.model_dump(), "episode": {**project.structuredContent.episode.model_dump(), "visualPlan": plan_data}}})
    coverage = validate_visuals(batch_id, item_id)
    return {"sceneId": scene_id, "coverage": coverage, "warnings": warnings}


def _output_is_current(output: dict | None, expected_hash: str, *, path_key: str, directory: bool) -> bool:
    if not isinstance(output, dict) or output.get("status") != "succeeded":
        return False
    if output.get("inputHash") != expected_hash:
        return False
    value = output.get(path_key)
    if not value:
        return False
    path = Path(str(value))
    return path.is_dir() if directory else path.is_file()


def _discard_output(row: dict, name: str) -> None:
    """Mark precisely one stale output for regeneration without touching its peer."""
    (row.get("outputs") or {}).pop(name, None)
    if name == "preview":
        row.pop("previewUrl", None)
    elif name == "jianying":
        row.pop("jianyingDraftPath", None)

def resume_item(batch_id: str, item_id: str) -> dict:
    batch,row=_item(batch_id,item_id)
    if not (row.get("visualCoverage") or {}).get("complete"): raise batches.BatchError("visual_coverage_incomplete","Visual coverage is incomplete")
    project=get_project(row.get("projectId"))
    if not project or not project.structuredContent: raise batches.BatchError("project_invalid","Structured project is invalid")
    plan=project.structuredContent.episode.visualPlan
    if not plan or plan.planId != row.get("visualPlanId") or plan.sourceHash != visual_source_hash(project.model_dump()): raise batches.BatchError("visual_plan_stale","Visual plan is stale")
    spec_payload,_=batches._load(batch_id); spec=batches.TemplateBatchSpec.model_validate(spec_payload)
    item=next(value for value in spec.items if value.itemId==item_id)
    outputs = item.outputs or spec.defaults.outputs
    variant_id = project.structuredContent.episode.activeVariantId or "publish"
    output_hash=factory_output_hash(project,variant_id,plan,outputs)
    completed = row.get("outputs") or {}
    preview_ok = not outputs.preview or _output_is_current(completed.get("preview"), output_hash, path_key="path", directory=False)
    jianying_ok = not outputs.jianyingDirect or _output_is_current(completed.get("jianying"), output_hash, path_key="draftPath", directory=True)
    if row.get("status") == "succeeded" and preview_ok and jianying_ok:
        return {"status":"succeeded","reused":True}
    if row.get("status") not in {"succeeded", "ready_to_resume", "failed"}:
        raise batches.BatchError("item_not_ready_to_resume","Item is not ready to resume")
    if not preview_ok:
        _discard_output(row, "preview")
    if not jianying_ok:
        _discard_output(row, "jianying")
    row.update({"status":"running","phase":"compiling_visuals"}); batches._save(batch_id,batch)
    try:
        batches._run_item_outputs(
            batch_id, item_id, row["projectId"], outputs, row,
            structured_variant_id=variant_id, input_hash=output_hash,
        )
    except Exception as exc:
        row.update({"status":"failed","phase":row.get("phase") or "rendering_preview","errorCode":"output_failed","error":str(exc)[:500]})
        batch["status"]=batches._aggregate_batch_status(batch["items"]); batches._save(batch_id,batch)
        raise
    row.update({"status":"succeeded","phase":"done","finishedAt":batches._now()}); batch["status"]=batches._aggregate_batch_status(batch["items"]); batches._save(batch_id,batch)
    return {"status":"succeeded","reused":False}

def resume_batch(batch_id: str) -> dict:
    _,batch=batches._load(batch_id); resumed=[]; waiting=[]; failed=[]; skipped=[]
    for row in batch["items"]:
        if row.get("status") in {"ready_to_resume","failed"}:
            try: resume_item(batch_id,row["itemId"]); resumed.append(row["itemId"])
            except Exception: failed.append(row["itemId"])
        elif row.get("status")=="awaiting_visual_assets": waiting.append(row["itemId"])
        elif row.get("status") == "succeeded": skipped.append(row["itemId"])
    latest=batches.get(batch_id)
    return {"batchId":batch_id,"status":latest.get("status"),"resumedItems":resumed,"waitingItems":waiting,"skippedItems":skipped,"failedItems":failed}

def continue_factory(batch_id: str) -> dict:
    batch=batches.get(batch_id); status=batch.get("status")
    if status=="awaiting_visual_assets": return pending_visuals(batch_id)
    if status=="ready_to_resume": return resume_batch(batch_id)
    return {"batchId":batch_id,"status":status,"items":batch.get("items",[])}
