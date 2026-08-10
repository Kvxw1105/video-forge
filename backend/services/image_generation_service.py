from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from models.image_generation import ImageGenerationBatch
from services.project_service import _project_dir, get_project
from shared.visual_scene import visual_source_hash


class ImageGenerationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _batch_dir(project_id: str) -> Path:
    return _project_dir(project_id) / "image-generation" / "batches"


def _batch_path(project_id: str, batch_id: str) -> Path:
    if not batch_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in batch_id):
        raise ImageGenerationError("invalid_batch_id", "Invalid image generation batch ID")
    return _batch_dir(project_id) / f"{batch_id}.json"


def _write_batch(batch: dict) -> dict:
    validated = ImageGenerationBatch.model_validate(batch)
    target = _batch_path(validated.projectId, validated.batchId)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f".json.tmp-{uuid4().hex}")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(validated.model_dump_json(indent=2))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return validated.model_dump(mode="json")


def get_batch(project_id: str, batch_id: str) -> dict:
    target = _batch_path(project_id, batch_id)
    if not target.is_file():
        raise ImageGenerationError("batch_not_found", f"Image generation batch not found: {batch_id}")
    try:
        return ImageGenerationBatch.model_validate_json(target.read_text(encoding="utf-8")).model_dump(mode="json")
    except (OSError, ValueError) as exc:
        raise ImageGenerationError("batch_invalid", f"Image generation batch is unreadable: {batch_id}") from exc


def _default_size(aspect_ratio: str) -> str:
    if aspect_ratio in {"9:16", "4:5"}:
        return "1024x1536"
    if aspect_ratio in {"16:9", "4:3"}:
        return "1536x1024"
    return "1024x1024"


def _final_prompt(values: dict) -> str:
    sections = [
        values.get("prompt") or values.get("sceneIntent") or values.get("text"),
        f"Subject: {values['subject']}" if values.get("subject") else "",
        f"Composition: {values['composition']}" if values.get("composition") else "",
        f"Visual style: {values['styleAnchor']}" if values.get("styleAnchor") else "",
        f"Continuity: {values['continuityAnchor']}" if values.get("continuityAnchor") else "",
        f"Framing: {values['safeArea']}" if values.get("safeArea") else "",
    ]
    return "\n".join(section.strip() for section in sections if str(section or "").strip())


def create_batch(
    project_id: str,
    *,
    channel: str = "agent",
    provider_id: str = "",
    model: str = "",
    size: str = "",
    candidate_count: int = 1,
    auto_approve: bool = False,
    style_anchor: str = "",
    continuity_anchor: str = "",
    scene_ids: list[str] | None = None,
    scene_overrides: dict[str, dict] | None = None,
) -> dict:
    project = get_project(project_id)
    if project is None:
        raise ImageGenerationError("project_not_found", f"Project not found: {project_id}")
    episode = project.structuredContent.episode if project.structuredContent else None
    plan = episode.visualPlan if episode else None
    if plan is None:
        raise ImageGenerationError("visual_plan_missing", "A timed VisualPlan is required before image generation")
    current_source_hash = visual_source_hash(project.model_dump())
    if plan.sourceHash != current_source_hash:
        raise ImageGenerationError("visual_plan_stale", "The VisualPlan is stale; regenerate it before image generation")
    if channel not in {"builtin", "agent"}:
        raise ImageGenerationError("invalid_channel", f"Unsupported image generation channel: {channel}")
    if not 1 <= int(candidate_count) <= 4:
        raise ImageGenerationError("invalid_candidate_count", "candidate_count must be between 1 and 4")

    selected = set(scene_ids or [])
    unknown = selected - {scene.id for scene in plan.scenes}
    if unknown:
        raise ImageGenerationError("scene_not_found", f"Unknown VisualPlan Scenes: {', '.join(sorted(unknown))}")
    subtitle_by_id = {subtitle.id: subtitle for subtitle in project.subtitles}
    block_by_id = {block.id: block for block in episode.blocks}
    overrides = scene_overrides or {}
    batch_id = f"image_batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    items = []
    for index, scene in enumerate(plan.scenes, 1):
        if selected and scene.id not in selected:
            continue
        subtitles = [subtitle_by_id[item] for item in scene.subtitleIds if item in subtitle_by_id]
        if len(subtitles) != len(scene.subtitleIds):
            raise ImageGenerationError("scene_timing_invalid", f"Scene {scene.id} references missing subtitles")
        start = min(float(item.start) for item in subtitles)
        end = max(float(item.end) for item in subtitles)
        if end <= start:
            raise ImageGenerationError("scene_timing_invalid", f"Scene {scene.id} has an invalid time window")
        override = overrides.get(scene.id) or {}
        text = "".join(item.text for item in subtitles)
        aspect_ratio = project.canvas.ratio
        item_size = str(override.get("size") or size or _default_size(aspect_ratio))
        values = {
            "sceneIntent": str(override.get("sceneIntent") or scene.summary or text),
            "subject": str(override.get("subject") or ""),
            "composition": str(override.get("composition") or ""),
            "styleAnchor": str(override.get("styleAnchor") or style_anchor),
            "continuityAnchor": str(override.get("continuityAnchor") or continuity_anchor),
            "safeArea": str(override.get("safeArea") or f"{aspect_ratio} frame, keep the lower subtitle-safe area uncluttered"),
            "prompt": str(override.get("prompt") or scene.prompt or scene.summary or text),
        }
        final_prompt = _final_prompt({**values, "text": text})
        if not final_prompt:
            raise ImageGenerationError("prompt_missing", f"Scene {scene.id} has no image Prompt")
        negative_prompt = str(override.get("negativePrompt") or scene.negativePrompt or "text, watermark, logo")
        hash_payload = {
            "projectId": project.id,
            "visualPlanId": plan.planId,
            "visualSourceHash": plan.sourceHash,
            "sceneId": scene.id,
            "blockId": scene.blockId,
            "subtitleIds": list(scene.subtitleIds),
            "start": start,
            "end": end,
            "finalPrompt": final_prompt,
            "negativePrompt": negative_prompt,
            "aspectRatio": aspect_ratio,
            "size": item_size,
            "providerId": provider_id,
            "model": model,
        }
        items.append(
            {
                "sceneId": scene.id,
                "blockId": scene.blockId,
                "subtitleIds": list(scene.subtitleIds),
                "start": start,
                "end": end,
                "duration": end - start,
                "text": text,
                **values,
                "negativePrompt": negative_prompt,
                "finalPrompt": final_prompt,
                "aspectRatio": aspect_ratio,
                "size": item_size,
                "inputHash": _canonical_hash(hash_payload),
                "expectedFilename": f"scene_{index:03d}.png",
                "status": "pending",
                "candidates": [],
            }
        )
    if not items:
        raise ImageGenerationError("scene_selection_empty", "Select at least one VisualPlan Scene")
    now = _now()
    batch = {
        "schemaVersion": 1,
        "batchId": batch_id,
        "projectId": project.id,
        "visualPlanId": plan.planId,
        "visualSourceHash": plan.sourceHash,
        "channel": channel,
        "providerId": provider_id,
        "model": model,
        "size": size,
        "candidateCount": candidate_count,
        "autoApprove": auto_approve,
        "status": "awaiting_agent" if channel == "agent" else "pending",
        "items": items,
        "createdAt": now,
        "updatedAt": now,
    }
    return _write_batch(batch)
