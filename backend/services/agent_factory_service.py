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
from services import image_generation_service as image_generation
from shared.visual_scene import visual_source_hash
from shared.production_profiles import compile_profile
from services.factory_visual_orchestrator import run_factory_visuals

@dataclass(frozen=True)
class FactoryStageResult:
    outcome: Literal["continue", "awaiting_visual_assets", "awaiting_visual_approval"]
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

    # v3 converts the old visual pause into an executable local production
    # stage.  The same image-generation batch, candidate, approval and bind
    # lifecycle is used; only the Factory policy decides whether to pause.
    if spec.productionMode in {"auto", "review"} and spec.productionProfile:
        profile = compile_profile(spec.productionProfile, (workflow.get("profileOverrides") or {}))
        workflow = {**workflow, "compiledProfile": profile}
        item_result["productionProfile"] = profile.model_dump(mode="json")
        item_result["productionMode"] = spec.productionMode

        def _progress(phase: str, message: str) -> None:
            item_result["phase"] = phase
            item_result["progressMessage"] = message
            _, current_batch = batches._load(batch_id)
            current_row = next((row for row in current_batch["items"] if row.get("itemId") == item.itemId), None)
            if current_row is not None:
                current_row.update(item_result)
            batches._save(batch_id, current_batch)

        try:
            visual_result = run_factory_visuals(project.id, spec, workflow=workflow, update=_progress)
        except Exception as exc:
            code = getattr(exc, "code", "visual_generation_failed")
            raise batches.BatchError(code, str(exc)) from exc
        batch_payloads = [value for value in visual_result.batches]
        batch_ids = [str(value.get("batchId")) for value in batch_payloads if value.get("batchId")]
        bound_scenes = []
        if visual_result.outcome == "bound":
            refreshed = get_project(project.id)
            current_plan = refreshed.structuredContent.episode.visualPlan if refreshed and refreshed.structuredContent else None
            bound_scenes = [scene.id for scene in (current_plan.scenes if current_plan else []) if scene.primaryAssetId]
        coverage = {"totalScenes": len(expected), "boundScenes": len(bound_scenes), "missingScenes": [row["sceneId"] for row in expected if row["sceneId"] not in set(bound_scenes)], "invalidScenes": [], "complete": len(bound_scenes) == len(expected)}
        patch = {"visualPlanId": plan.planId if hasattr(plan,"planId") else plan["planId"], "generationPackPath": pack["path"], "expectedScenes": expected, "visualBatchId": batch_ids[0] if batch_ids else None, "visualBatchIds": batch_ids, "visualCoverage": coverage, "visualReview": {"required": visual_result.outcome == "awaiting_visual_approval", "candidateCount": profile.candidateCount, "profileId": profile.id}}
        if visual_result.outcome == "awaiting_visual_approval":
            return FactoryStageResult("awaiting_visual_approval", patch)
        return FactoryStageResult("continue", patch)

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
        if row.get("status") not in {"awaiting_visual_assets", "awaiting_visual_approval"}: continue
        project = get_project(row.get("projectId"))
        plan = project.structuredContent.episode.visualPlan if project and project.structuredContent else None
        if not plan: continue
        items.append({"itemId":row["itemId"],"projectId":row["projectId"],"status":row.get("status"),"productionMode":row.get("productionMode"),"productionProfile":row.get("productionProfile"),"visualPlanId":plan.planId,"generationPackPath":row.get("generationPackPath"),"visualBatchId":row.get("visualBatchId"),"visualBatchIds":row.get("visualBatchIds") or [],"scenes":[{"sceneId":scene.id,"prompt":scene.prompt,"negativePrompt":scene.negativePrompt,"requestedMediaType":scene.requestedMediaType,"aspectRatio":project.canvas.ratio,"expectedFilename":f"scene_{index:03d}.png"} for index,scene in enumerate(plan.scenes,1)]})
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
    visual_batches = []
    for visual_batch_id in row.get("visualBatchIds") or ([row.get("visualBatchId")] if row.get("visualBatchId") else []):
        try:
            visual_batches.append(image_generation.get_batch(project.id, visual_batch_id))
        except Exception:
            continue
    return {"batchId": batch_id, "itemId": item_id, "projectId": project.id, "itemName": project.name, "status": row.get("status"), "productionMode": row.get("productionMode"), "productionProfile": row.get("productionProfile"), "visualPlanId": plan.planId, "sourceHash": plan.sourceHash, "audio": {"url": f"/api/projects/{project.id}/assets/stream?path={audio_path}" if audio_path else "", "duration": audio_duration}, "coverage": row.get("visualCoverage") or {"totalScenes": len(scenes), "boundScenes": sum(bool(item["boundAsset"]) for item in scenes), "missingScenes": [item["sceneId"] for item in scenes if not item["boundAsset"]], "complete": all(item["boundAsset"] for item in scenes)}, "scenes": scenes, "visualBatches": visual_batches}


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


def approve_and_continue(batch_id: str, item_id: str, selections: list[dict]) -> dict:
    """Approve all selected candidates in the Review gate, then resume outputs."""
    batch, row = _item(batch_id, item_id)
    if row.get("status") != "awaiting_visual_approval":
        raise batches.BatchError("item_not_awaiting_visual_approval", "Item is not waiting for visual approval")
    project_id = row.get("projectId")
    batch_ids = row.get("visualBatchIds") or ([row.get("visualBatchId")] if row.get("visualBatchId") else [])
    if not batch_ids:
        raise batches.BatchError("visual_batch_missing", "Visual generation batch is unavailable")
    project = get_project(project_id)
    current_source_hash = visual_source_hash(project.model_dump()) if project else ""
    # Incremental reruns retain historical batch IDs for audit, but only the
    # current-source batch may be approved against the new VisualPlan.
    current_batches = []
    for visual_batch_id in batch_ids:
        visual_batch = image_generation.get_batch(project_id, visual_batch_id)
        if visual_batch.get("visualSourceHash") == current_source_hash:
            current_batches.append(visual_batch_id)
    batch_ids = current_batches
    if not batch_ids:
        raise batches.BatchError("visual_batch_missing", "No current visual generation batch is available")
    selected_by_batch: dict[str, list[dict]] = {str(batch_id): [] for batch_id in batch_ids}
    requested = {str(item.get("sceneId")): str(item.get("candidateId")) for item in selections}
    for visual_batch_id in batch_ids:
        visual_batch = image_generation.get_batch(project_id, visual_batch_id)
        for visual_item in visual_batch.get("items", []):
            if visual_item.get("status") not in {"generated", "approved", "bound"} or not visual_item.get("candidates"):
                continue
            available = {str(candidate["candidateId"]) for candidate in visual_item.get("candidates") or []}
            candidate_id = requested.get(str(visual_item["sceneId"])) if requested.get(str(visual_item["sceneId"])) in available else visual_item["candidates"][0]["candidateId"]
            selected_by_batch[visual_batch_id].append({"sceneId": visual_item["sceneId"], "candidateId": candidate_id})
    for visual_batch_id, values in selected_by_batch.items():
        if values:
            image_generation.approve_candidates(project_id, visual_batch_id, values, approval_policy="review_gate", approved_by="user")
    coverage = validate_visuals(batch_id, item_id)
    if not coverage.get("complete"):
        raise batches.BatchError("visual_coverage_incomplete", "Review approval did not cover every Scene")
    return resume_item(batch_id, item_id)


def _refresh_plan_after_scene_edit(project, scene_id: str, text: str) -> None:
    """Persist a Scene text edit while retaining timing and other Scene assets."""
    if not project or not project.structuredContent:
        raise batches.BatchError("project_invalid", "Structured project is invalid")
    episode = project.structuredContent.episode
    plan = episode.visualPlan
    target = next((scene for scene in (plan.scenes if plan else []) if scene.id == scene_id), None)
    if not target:
        raise batches.BatchError("scene_not_found", f"Scene not found: {scene_id}")
    subtitle_map = {subtitle.id: subtitle.model_dump() for subtitle in project.subtitles}
    target_ids = list(target.subtitleIds)
    if not target_ids:
        raise batches.BatchError("scene_timing_invalid", "Scene has no subtitle timing")
    # Keep every timestamp stable.  The edited narration is placed in the
    # first subtitle window and remaining windows stay as empty timing slots.
    subtitle_map[target_ids[0]]["text"] = str(text or "").strip()
    for subtitle_id in target_ids[1:]:
        subtitle_map[subtitle_id]["text"] = ""
    subtitles = [subtitle_map[subtitle.id] for subtitle in project.subtitles]
    blocks = []
    for block in episode.blocks:
        block_data = block.model_dump()
        binding = next((value for value in episode.bindings if value.blockId == block.id), None)
        if binding:
            block_data["text"] = "".join(subtitle_map[item] ["text"] for item in binding.subtitleIds if item in subtitle_map)
            block_data["revision"] = int(block_data.get("revision") or 1) + 1
        blocks.append(block_data)
    plan_data = plan.model_dump()
    for scene_data in plan_data["scenes"]:
        if scene_data["id"] == scene_id:
            scene_data["visualAssetIds"] = []
            scene_data["primaryAssetId"] = None
    structured = project.structuredContent.model_dump()
    structured["episode"]["blocks"] = blocks
    structured["episode"]["visualPlan"] = plan_data
    updated = update_project(project.id, {"subtitles": subtitles, "structuredContent": structured})
    if not updated:
        raise batches.BatchError("project_missing", "Project is unavailable")
    refreshed = updated.model_dump()
    refreshed_plan = refreshed["structuredContent"]["episode"]["visualPlan"]
    refreshed_plan["sourceHash"] = visual_source_hash(refreshed)
    update_project(updated.id, {"structuredContent": {**refreshed["structuredContent"], "episode": {**refreshed["structuredContent"]["episode"], "visualPlan": refreshed_plan}}})


def edit_scene_and_rerun(batch_id: str, item_id: str, scene_id: str, text: str, provider_id: str = "") -> dict:
    """Edit one Scene's narration, preserve timing, and rerun only that Scene."""
    _, row = _item(batch_id, item_id)
    project = get_project(row.get("projectId"))
    _refresh_plan_after_scene_edit(project, scene_id, text)
    return regenerate_visual(batch_id, item_id, scene_id, provider_id)


def regenerate_visual(batch_id: str, item_id: str, scene_id: str, provider_id: str = "") -> dict:
    """Regenerate one stale/review Scene through the shared Provider lifecycle."""
    _, row = _item(batch_id, item_id)
    if row.get("status") not in {"succeeded", "awaiting_visual_approval", "ready_to_resume", "awaiting_visual_assets"}:
        raise batches.BatchError("item_not_ready_for_visual_regeneration", "Item is not in a visual regeneration state")
    project = get_project(row.get("projectId"))
    profile_id = row.get("productionProfile") or "balanced_auto"
    from shared.production_profiles import get_profile
    profile = get_profile(profile_id)
    route = provider_id if provider_id in {"stickman", "code_visual"} else profile.routingMode
    created = image_generation.create_batch(
        project.id,
        channel="local",
        routing_mode=route,
        candidate_count=int(profile.candidateCount),
        style_anchor=profile.styleAnchor,
        continuity_anchor=profile.continuityAnchor,
        scene_ids=[scene_id],
        scene_overrides={scene_id: {"providerId": route, "outputMode": "static" if profile.motionPreference == "static" else "video", "durationPolicy": profile.durationPolicy}},
    )
    generated = image_generation.run_local_batch(project.id, created["batchId"])
    row.setdefault("visualBatchIds", []).append(created["batchId"])
    row["visualBatchId"] = created["batchId"]
    current_scenes = list(project.structuredContent.episode.visualPlan.scenes)
    current_bound = [scene.id for scene in current_scenes if scene.primaryAssetId]
    row["visualCoverage"] = {"totalScenes": len(current_scenes), "boundScenes": len(current_bound), "missingScenes": [scene.id for scene in current_scenes if not scene.primaryAssetId], "invalidScenes": [], "complete": len(current_bound) == len(current_scenes)}
    row["status"] = "awaiting_visual_approval"
    row["phase"] = "awaiting_visual_approval"
    _, current_batch = batches._load(batch_id)
    current_row = next(value for value in current_batch["items"] if value["itemId"] == item_id)
    current_row.update(row)
    batches._save(batch_id, current_batch)
    if row.get("productionMode") == "auto":
        visual_batch = image_generation.get_batch(project.id, created["batchId"])
        selections = [{"sceneId": item["sceneId"], "candidateId": item["candidates"][0]["candidateId"]} for item in visual_batch.get("items", []) if item.get("candidates")]
        if selections:
            image_generation.approve_candidates(project.id, created["batchId"], selections, approval_policy=f"profile:{profile.id}:incremental", approved_by="videoforge:auto")
        coverage = validate_visuals(batch_id, item_id)
        if coverage.get("complete"):
            return {"generation": generated, "details": item_visuals(batch_id, item_id), "resume": resume_item(batch_id, item_id)}
    return {"generation": generated, "details": item_visuals(batch_id, item_id)}

def continue_factory(batch_id: str) -> dict:
    batch=batches.get(batch_id); status=batch.get("status")
    if status in {"awaiting_visual_assets", "awaiting_visual_approval"}: return pending_visuals(batch_id)
    if status=="ready_to_resume": return resume_batch(batch_id)
    return {"batchId":batch_id,"status":status,"items":batch.get("items",[])}
