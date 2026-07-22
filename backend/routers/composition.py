from __future__ import annotations
from fastapi import APIRouter, HTTPException
from config import JIANYING_DRAFT_DIR
from services.project_service import get_project, list_projects, _project_dir, resolve_project_paths
from shared.structured_composition import compile_structured_composition
from engines.renderer import render_preview
from adapters.jianying import generate_jianying_draft

router = APIRouter(tags=["composition"])

def _load_source(source_id: str):
    return get_project(source_id)

def _resolve_source(source_id: str, value: dict) -> dict:
    return resolve_project_paths(_project_dir(source_id), value)

def _compiled(project_id: str):
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if project.composition is None:
        raise HTTPException(409, "Project does not contain composition")
    try:
        return project, compile_structured_composition(project, _load_source, _resolve_source)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error

@router.get("/api/projects/structured/catalog")
def structured_catalog():
    results = []
    for item in list_projects():
        project = get_project(item["id"])
        if not project or project.structuredContent is None:
            continue
        episode = project.structuredContent.episode
        has_alignment = any((subtitle.metadata or {}).get("generatedBy") == "fish_timestamp_alignment" for subtitle in project.subtitles)
        results.append({"projectId": project.id, "name": project.name, "episodeId": episode.episodeId, "episodeTitle": episode.title, "variants": [{"id": variant.id, "name": variant.name, "blockCount": len(variant.blockIds)} for variant in episode.variants], "hasAlignment": has_alignment, "hasBindings": bool(episode.bindings), "hasAudio": bool(project.audio.voiceovers or project.audio.voiceover.file), "updatedAt": project.updated_at, "warnings": []})
    return results

@router.post("/api/projects/{project_id}/composition/compile")
def compile_composition(project_id: str):
    _, compiled = _compiled(project_id)
    return {"compositionId": compiled.composition_id, "title": compiled.title, "itemCount": len(compiled.items), "duration": compiled.total_duration, "voiceoverClipCount": sum(item.voiceover_clip_count for item in compiled.items), "visualClipCount": sum(item.visual_clip_count for item in compiled.items), "subtitleCount": sum(item.subtitle_count for item in compiled.items), "items": [item.__dict__ for item in compiled.items], "warnings": list(compiled.warnings)}

@router.post("/api/projects/{project_id}/composition/preview")
def preview_composition(project_id: str):
    _, compiled = _compiled(project_id)
    output = _project_dir(project_id) / "preview_composition.mp4"
    try:
        output.unlink(missing_ok=True)
        render_preview(compiled.project_view, output)
    except Exception as error:
        output.unlink(missing_ok=True)
        raise HTTPException(500, f"Composition preview failed: {error}") from error
    return {"status": "ok", "previewUrl": f"/api/projects/{project_id}/assets/project-file/{output.name}", "duration": compiled.total_duration + 0.5, "itemCount": len(compiled.items), "warnings": list(compiled.warnings)}

@router.post("/api/projects/{project_id}/composition/export/jianying-direct")
def export_composition(project_id: str, policy: str = "create_new"):
    if policy != "create_new":
        raise HTTPException(400, "composition direct export only supports policy=create_new")
    if not JIANYING_DRAFT_DIR:
        raise HTTPException(400, "未检测到剪映草稿目录")
    _, compiled = _compiled(project_id)
    try:
        result = generate_jianying_draft(compiled.project_view, output_dir=JIANYING_DRAFT_DIR, policy="create_new", direct_export=True)
        return {"status": "ok", "compositionId": compiled.composition_id, "duration": compiled.total_duration, "itemCount": len(compiled.items), "warnings": list(dict.fromkeys((*compiled.warnings, *result.warnings))), **result.to_metadata()}
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    except Exception as error:
        raise HTTPException(500, f"Composition JianYing export failed: {error}") from error
