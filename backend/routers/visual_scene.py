from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from models.project import StructuredVisualPlan
from services.project_service import _project_dir, get_project, update_project
from shared.structured_content import compile_structured_media_variant
from shared.visual_scene import planning_context, propose_scenes, validate_plan, visual_source_hash

router = APIRouter(prefix="/api/projects/{project_id}/visual-plan", tags=["visual-scenes"])
_MEDIA = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm"}


def _project(project_id: str):
    project = get_project(project_id)
    if not project: raise HTTPException(404, "Project not found")
    if not project.structuredContent: raise HTTPException(409, "Project does not contain structuredContent")
    return project


def _conflict(project, data: dict):
    expected=data.get("expectedUpdatedAt")
    if expected is not None and expected != project.updated_at:
        raise HTTPException(409, {"code":"project_changed", "expectedUpdatedAt":expected, "actualUpdatedAt":project.updated_at})


@router.get("/context")
def context(project_id: str): return planning_context(_project(project_id).model_dump())


@router.post("/propose")
def propose(project_id: str, data: dict):
    project=_project(project_id); _conflict(project, data)
    settings=data.get("settings") or {"mode":data.get("mode", "hybrid"), "unitsPerScene":data.get("unitsPerScene",3), "targetDuration":data.get("targetDuration",7), "minDuration":data.get("minDuration",3), "maxDuration":data.get("maxDuration",12)}
    episode = project.structuredContent.episode
    return {"sourceHash":visual_source_hash(project.model_dump()), "alignmentGenerationId":episode.alignment.generationId if episode.alignment else None, "settings":settings, "scenes":propose_scenes(project.model_dump(), settings)}


@router.get("")
def get_plan(project_id: str):
    episode=_project(project_id).structuredContent.episode
    return episode.visualPlan.model_dump() if episode.visualPlan else {"visualPlan":None}


@router.put("")
def set_plan(project_id: str, data: dict):
    project=_project(project_id); _conflict(project, data)
    raw=data.get("plan") or data
    raw={**raw, "planId":raw.get("planId") or f"plan_{uuid4().hex[:12]}", "sourceHash":raw.get("sourceHash") or visual_source_hash(project.model_dump()), "alignmentGenerationId":raw.get("alignmentGenerationId", project.structuredContent.episode.alignment.generationId if project.structuredContent.episode.alignment else None)}
    try: plan=StructuredVisualPlan.model_validate(raw)
    except Exception as exc: raise HTTPException(422, str(exc)) from exc
    errors=validate_plan(project.model_dump(), plan.model_dump())
    if errors: raise HTTPException(422, {"code":"invalid_visual_plan", "errors":errors})
    updated=update_project(project_id,{"structuredContent":{**project.structuredContent.model_dump(),"episode":{**project.structuredContent.episode.model_dump(),"visualPlan":plan.model_dump()}}})
    return {"projectId":updated.id,"updatedAt":updated.updated_at,"plan":plan.model_dump()}


@router.post("/validate")
def validate(project_id: str, data: dict | None=None):
    project=_project(project_id); plan=(data or {}).get("plan") or (project.structuredContent.episode.visualPlan.model_dump() if project.structuredContent.episode.visualPlan else None)
    if not plan: raise HTTPException(404,"Visual plan not found")
    errors=validate_plan(project.model_dump(), plan)
    return {"valid":not errors,"errors":errors,"sourceHash":visual_source_hash(project.model_dump())}


@router.post("/generation-pack")
def generation_pack(project_id: str):
    project=_project(project_id); plan=project.structuredContent.episode.visualPlan
    if not plan: raise HTTPException(404,"Visual plan not found")
    errors=validate_plan(project.model_dump(),plan.model_dump())
    if errors: raise HTTPException(422,{"code":"invalid_visual_plan","errors":errors})
    directory=_project_dir(project_id)/"visual-generation"/plan.planId; directory.mkdir(parents=True,exist_ok=True)
    raw = project.model_dump()
    subtitles = {item.get("id"): item for item in raw.get("subtitles") or []}
    rows=[]
    for index,scene in enumerate(plan.scenes,1):
        ids = list(scene.subtitleIds)
        start = float(subtitles[ids[0]].get("start", 0)) if ids else 0.0
        end = float(subtitles[ids[-1]].get("end", start)) if ids else start
        rows.append({"sceneId":scene.id,"blockId":scene.blockId,"subtitleIds":ids,"start":start,"end":end,"duration":end-start,"text":"".join(str(subtitles[item].get("text") or "") for item in ids if item in subtitles),"summary":scene.summary,"prompt":scene.prompt,"negativePrompt":scene.negativePrompt,"mediaType":scene.requestedMediaType,"visualPolicy":scene.metadata.get("visualPolicy", {}),"aspectRatio":project.canvas.ratio,"expectedFilename":f"scene_{index:03d}.png"})
    (directory/"visual-plan.json").write_text(plan.model_dump_json(indent=2),encoding="utf-8"); (directory/"prompts.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
    with (directory/"prompts.csv").open("w",encoding="utf-8",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=rows[0].keys() if rows else ["sceneId"]); writer.writeheader(); writer.writerows(rows)
    (directory/"README.md").write_text("Place scene_### image or video files here, then import by folder.\n",encoding="utf-8")
    return {"planId":plan.planId,"path":str(directory),"files":[str(path.name) for path in directory.iterdir()]}


@router.post("/import-folder")
def import_folder(project_id: str, data: dict):
    project=_project(project_id); _conflict(project,data); plan=project.structuredContent.episode.visualPlan
    if not plan: raise HTTPException(404,"Visual plan not found")
    folder=Path(str(data.get("folder") or "")); manifest=data.get("manifest") or {}
    if not folder.is_dir() and not manifest: raise HTTPException(422,"folder or manifest is required")
    by_scene={scene.id:scene.model_dump() for scene in plan.scenes}; assets=list(project.assets); target=_project_dir(project_id)/"assets"; target.mkdir(exist_ok=True); imported=[]
    replace = bool(data.get("replace", False))
    selections = []
    for index,scene in enumerate(plan.scenes,1):
        candidates=[Path(manifest[scene.id])] if scene.id in manifest else list(folder.glob(f"{scene.id}*"))+list(folder.glob(f"scene_{index:03d}*"))
        chosen=next((path for path in candidates if path.is_file() and path.suffix.lower() in _MEDIA),None)
        if not chosen: continue
        destination=target/f"{scene.id}{chosen.suffix.lower()}"
        selections.append((scene, chosen, destination))
    # Do the conflict pass before copying anything: a failed import cannot alter
    # a prior scene binding or overwrite a generated asset by accident.
    for scene, chosen, destination in selections:
        if destination.exists() and not replace and _file_digest(destination) != _file_digest(chosen):
            raise HTTPException(409, {"code":"asset_conflict", "message":f"Generated asset conflicts with existing scene asset: {scene.id}"})
    for scene, chosen, destination in selections:
        if not destination.exists() or replace:
            shutil.copy2(chosen,destination)
        asset_id=f"visual_{scene.id}"; assets=[asset for asset in assets if (asset.id if hasattr(asset,"id") else asset.get("id"))!=asset_id]; assets.append({"id":asset_id,"type":"video" if chosen.suffix.lower() in {'.mp4','.mov','.webm'} else "image","name":destination.name,"path":(Path('assets')/destination.name).as_posix(),"metadata":{}})
        by_scene[scene.id]["visualAssetIds"]=[asset_id]; by_scene[scene.id]["primaryAssetId"]=asset_id; imported.append(scene.id)
    new_plan={**plan.model_dump(),"scenes":[by_scene[scene.id] for scene in plan.scenes]}
    updated=update_project(project_id,{"assets":assets,"structuredContent":{**project.structuredContent.model_dump(),"episode":{**project.structuredContent.episode.model_dump(),"visualPlan":new_plan}}})
    return {"imported":imported,"updatedAt":updated.updated_at}


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@router.post("/compile/{variant_id}")
def compile_variant(project_id: str, variant_id: str):
    project=_project(project_id)
    try:
        compiled=compile_structured_media_variant(project,variant_id)
    except (ValueError,KeyError) as exc: raise HTTPException(422,str(exc)) from exc
    return {"variantId":variant_id,"segments":compiled.project_view["segments"],"duration":compiled.total_duration,"warnings":list(compiled.warnings)}
