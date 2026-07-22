from __future__ import annotations
import json
import threading
from pathlib import Path
from fastapi import APIRouter, HTTPException
from services.project_service import get_project, _project_dir
from routers.settings import get_tts_settings_raw
from services.fish_timestamp_tts import request_fish_timestamp, FishTimestampError
from services.structured_audio_materializer import episode_text, has_structured_alignment, materialize_structured_audio, validate_structured_audio_cache

router = APIRouter(prefix="/api/projects/{project_id}/structured/audio", tags=["structured-audio"])
_PROJECT_LOCKS: dict[str, threading.Lock] = {}


@router.get("/status")
def structured_audio_status(project_id: str):
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if project.structuredContent is None:
        raise HTTPException(409, "Project does not contain structuredContent")
    settings = get_tts_settings_raw()
    episode = project.structuredContent.episode
    record = episode.alignment.model_dump() if episode.alignment else None
    data = {"structured": True, "fishConfigured": bool(settings.fishApiKey), "referenceConfigured": bool(settings.fishReferenceId), "hasAlignment": has_structured_alignment(project.model_dump(), episode.episodeId), "generationId": None, "voiceoverId": None, "audioDuration": 0, "blockCount": 0, "subtitleCount": 0, "overallConfidence": 0, "warnings": []}
    if record:
        try:
            manifest = json.loads((_project_dir(project_id) / record["manifestPath"]).read_text(encoding="utf-8"))
            data.update({key: manifest.get(key, data[key]) for key in ("generationId", "voiceoverId", "audioDuration", "overallConfidence", "warnings")})
            data["blockCount"] = len(manifest.get("blockRanges", []))
            data["subtitleCount"] = sum(1 for item in project.subtitles if (item.metadata or {}).get("generationId") == data["generationId"])
        except Exception:
            data["warnings"] = ["alignment manifest could not be read"]
    return data


@router.post("/fish-aligned")
def generate_fish_aligned(project_id: str, data: dict | None = None):
    data = data or {}
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if project.structuredContent is None:
        raise HTTPException(409, "Project does not contain structuredContent")
    settings = get_tts_settings_raw()
    if not settings.fishApiKey:
        raise HTTPException(409, "Fish Audio API 未配置")
    reference_id = str(data.get("referenceId") or settings.fishReferenceId or "").strip()
    if not reference_id:
        raise HTTPException(409, "referenceId 未提供")
    project_dict = project.model_dump()
    expected_updated_at = data.get("expectedUpdatedAt")
    if expected_updated_at is not None and expected_updated_at != project.updated_at:
        raise HTTPException(409, "structured_project_changed_during_generation")
    text, blocks = episode_text(project_dict, data.get("blockIds"))
    if not text:
        raise HTTPException(422, "Block 文本为空")
    options = {**data, "referenceId": reference_id, "model": str(data.get("model") or settings.fishModel or "s2-pro")}
    if data.get("force"):
        cache_status = "forced"
    else:
        cache_hit, cache_status, manifest = validate_structured_audio_cache(project_dict, _project_dir(project_id), options, blocks)
        if cache_hit:
            record = project.structuredContent.episode.alignment
            return {"status": "ok", "cached": True, "cacheStatus": "hit", "liveCallPerformed": False, "generationId": record.generationId, "voiceoverId": record.voiceoverId, "audioDuration": manifest.get("audioDuration", 0), "blockCount": len(manifest.get("blockRanges", [])), "subtitleCount": sum(1 for sub in project.subtitles if (sub.metadata or {}).get("generationId") == record.generationId), "overallConfidence": record.overallConfidence, "blockRanges": manifest.get("blockRanges", []), "warnings": manifest.get("warnings", [])}
    lock = _PROJECT_LOCKS.setdefault(project_id, threading.Lock())
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "该项目已有 Fish Audio 生成任务正在运行")
    try:
        parsed = request_fish_timestamp(
            text, settings.fishApiKey, reference_id,
            model=str(data.get("model") or settings.fishModel or "s2-pro"),
            fmt=str(data.get("format") or "wav"), latency=str(data.get("latency") or "normal"),
            chunk_length=int(data.get("chunkLength", 200)), condition_on_previous_chunks=bool(data.get("conditionOnPreviousChunks", True)),
            temperature=float(data.get("temperature", 0.7)), top_p=float(data.get("topP", 0.7)),
            prosody={"speed": float(data.get("speed", 1.0)), "volume": float(data.get("volume", 0))},
        )
        current = get_project(project_id)
        if not current or current.updated_at != project.updated_at or current.structuredContent.episode.model_dump() != project.structuredContent.episode.model_dump():
            raise HTTPException(409, "structured_project_changed_during_generation")
        return {"status": "ok", "cached": False, "cacheStatus": cache_status, "liveCallPerformed": True, **materialize_structured_audio(project_id, project_dict, parsed, project_dir=_project_dir(project_id), options=options, block_ids=data.get("blockIds"))}
    except ValueError as exc:
        if str(exc) == "alignment_confidence_too_low":
            raise HTTPException(422, "alignment_confidence_too_low") from exc
        raise HTTPException(422, str(exc)) from exc
    except FishTimestampError as exc:
        status = exc.status_code if exc.status_code in {429, 502} else 502 if not exc.status_code else exc.status_code
        raise HTTPException(status, str(exc)) from exc
    finally:
        lock.release()
