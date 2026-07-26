from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from models.project import StructuredContent
from services.project_service import create_project_from_payload, get_project, update_project
from shared.structured_import import MAX_SOURCE_CHARS, parse_structured_markdown
from shared.structured_presets import build_blocks, build_default_structured_variants
from shared.structured_content import compile_structured_variant
from shared.presentation_templates import list_presentation_templates
from services.structured_audio_materializer import has_structured_alignment
from agent_runtime.raw_script_organizer import OrganizerError, organize_block, organize_source

router = APIRouter(prefix="/api", tags=["structured-authoring"])


@router.get("/structured/presentation-templates")
def get_presentation_templates():
    return {"templates": list_presentation_templates()}


def _suggested_id(block_type: str | None, index: int, blocks: list[dict]) -> str | None:
    if not block_type:
        return None
    prefix = {"CTA_TAG": "cta", "SHORT_OUTRO": "short_outro", "BRIDGE_IN": "bridge_in", "BRIDGE_OUT": "bridge_out", "COMMENT_CTA": "comment_cta"}.get(block_type, block_type.lower())
    occurrence = sum(1 for b in blocks[:index] if b.get("type") == block_type) + 1
    return f"{prefix}_{occurrence:02d}"


def _episode_from_payload(data: dict) -> dict:
    episode = data.get("episode") or {}
    blocks = []
    for raw in episode.get("blocks") or []:
        if not isinstance(raw, dict):
            continue
        metadata = dict(raw.get("metadata") or {})
        if raw.get("warnings"):
            metadata["organizerWarnings"] = list(raw["warnings"])
        blocks.append({key: raw[key] for key in ("id", "type", "text", "enabled", "revision") if key in raw} | {"metadata": metadata})
    variants = episode.get("variants") or []
    if not blocks or not variants:
        raise HTTPException(422, "episode requires blocks and variants")
    try:
        content = StructuredContent(schemaVersion=1, episode={**episode, "blocks": blocks, "variants": variants, "bindings": episode.get("bindings") or []})
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    episode_data = content.model_dump(mode="python")
    active = next((item for item in episode_data["episode"]["variants"] if item["id"] == episode_data["episode"].get("activeVariantId")), None)
    if not active or not active["blockIds"]:
        raise HTTPException(422, "activeVariantId must reference a non-empty variant")
    known = {item["id"]: item for item in episode_data["episode"]["blocks"]}
    if not any(known[item].get("enabled", True) and str(known[item].get("text") or "").strip() for item in active["blockIds"]):
        raise HTTPException(422, "active variant requires an enabled block with text")
    return episode_data



@router.post("/structured/import/parse")
def parse_import(data: dict):
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(422, "structured source text must not be empty")
    if len(text) > MAX_SOURCE_CHARS:
        raise HTTPException(413, f"structured source text exceeds {MAX_SOURCE_CHARS} characters")
    document = parse_structured_markdown(text)
    preview_blocks = build_blocks(list(document.sections))
    sections = []
    for index, section in enumerate(document.sections):
        sections.append({"index": index, "sourceHeading": section.source_heading, "detectedType": section.detected_type, "suggestedId": _suggested_id(section.detected_type, index, preview_blocks), "text": section.text, "sourceStartLine": section.source_start_line, "sourceEndLine": section.source_end_line, "warnings": list(section.warnings)})
    return {"title": document.title, "sections": sections, "unknownSectionCount": sum(s.detected_type is None for s in document.sections), "emptySectionCount": sum(not s.text.strip() for s in document.sections), "warnings": list(document.warnings)}


@router.post("/structured/import/organize")
def organize_raw_import(data: dict):
    try:
        return organize_source(str(data.get("text") or ""))
    except OrganizerError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/structured/import/organize-block")
def organize_single_block(data: dict):
    try:
        return organize_block(str(data.get("text") or ""), str(data.get("type") or "") or None)
    except OrganizerError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/projects/structured")
def create_structured(data: dict):
    episode = _episode_from_payload(data)
    name = str(data.get("name") or episode["episode"].get("title") or "Structured Episode").strip()
    ratio = str((data.get("canvas") or {}).get("ratio") or "9:16")
    if ratio not in {"9:16", "16:9", "1:1", "4:5", "4:3"}:
        raise HTTPException(422, "unsupported canvas ratio")
    from datetime import datetime
    from uuid import uuid4
    pid = f"proj_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
    active_id = episode["episode"].get("activeVariantId")
    script = compile_structured_variant({"structuredContent": episode}, active_id).script
    dimensions = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350), "4:3": (1440, 1080)}[ratio]
    now = datetime.now().isoformat()
    payload = {"id": pid, "name": name, "templateId": "structured_episode", "canvas": {"ratio": ratio, "width": dimensions[0], "height": dimensions[1]}, "structuredContent": episode, "script": script, "composition": None, "assets": [], "segments": [], "subtitles": [], "audio": {"voiceover": {}, "voiceovers": [], "bgm": {"tracks": []}, "sfx": []}, "created_at": now, "updated_at": now, "exportSettings": {"outputDir": ""}}
    project = create_project_from_payload(payload)
    return project.model_dump()


@router.get("/projects/{project_id}/structured/draft")
def get_draft(project_id: str):
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if not project.structuredContent:
        raise HTTPException(409, "Project does not contain structuredContent")
    return {"projectId": project.id, "updatedAt": project.updated_at, "structuredContent": project.structuredContent.model_dump()}


@router.patch("/projects/{project_id}/structured/draft")
def update_draft(project_id: str, data: dict):
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if not project.structuredContent:
        raise HTTPException(409, "Project does not contain structuredContent")
    if has_structured_alignment(project.model_dump(), project.structuredContent.episode.episodeId):
        raise HTTPException(409, "structured_alignment_exists")
    expected = data.get("expectedUpdatedAt")
    if expected is not None and expected != project.updated_at:
        return {"status": "conflict", "expectedUpdatedAt": expected, "actualUpdatedAt": project.updated_at}
    episode = project.structuredContent.model_dump(mode="python")["episode"]
    allowed = {"title", "topic", "symbol", "blocks", "variants", "activeVariantId"}
    if any(key not in allowed and key not in {"expectedUpdatedAt", "invalidateAlignment"} for key in data):
        raise HTTPException(422, "structured draft contains immutable fields")
    candidate = {**episode, **{key: data[key] for key in allowed if key in data}}
    try:
        validated = StructuredContent(schemaVersion=1, episode=candidate)
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    script = compile_structured_variant({"structuredContent": validated.model_dump()}, validated.episode.activeVariantId).script
    updated = update_project(project_id, {"structuredContent": validated.model_dump(), "script": script})
    return {"projectId": updated.id, "updatedAt": updated.updated_at, "structuredContent": updated.structuredContent.model_dump()}
