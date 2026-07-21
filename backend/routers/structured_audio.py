from __future__ import annotations
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from services.project_service import get_project, _project_dir
from routers.settings import get_tts_settings_raw
from services.fish_timestamp_tts import request_fish_timestamp, FishTimestampError
from services.structured_audio_materializer import episode_text, materialize_structured_audio

router = APIRouter(prefix="/api/projects/{project_id}/structured/audio", tags=["structured-audio"])


@router.get("/status")
def structured_audio_status(project_id: str):
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if project.structuredContent is None:
        raise HTTPException(409, "Project does not contain structuredContent")
    settings = get_tts_settings_raw()
    manifests = sorted(_project_dir(project_id).glob("structured_alignment_*.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True)
    data = {"structured": True, "fishConfigured": bool(settings.fishApiKey), "referenceConfigured": bool(settings.fishReferenceId), "hasAlignment": bool(manifests), "generationId": None, "voiceoverId": None, "audioDuration": 0, "blockCount": 0, "subtitleCount": 0, "overallConfidence": 0, "warnings": []}
    if manifests:
        try:
            manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
            data.update({key: manifest.get(key, data[key]) for key in ("generationId", "voiceoverId", "audioDuration", "overallConfidence", "warnings")})
            data["blockCount"] = len(manifest.get("blocks", []))
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
    text, blocks = episode_text(project_dict, data.get("blockIds"))
    if not text:
        raise HTTPException(422, "Block 文本为空")
    if not data.get("force"):
        manifests = sorted(_project_dir(project_id).glob("structured_alignment_*.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True)
        if manifests:
            try:
                cached = json.loads(manifests[0].read_text(encoding="utf-8"))
                if cached.get("voiceoverId") and cached.get("overallConfidence", 0) >= 0.90:
                    return {"status": "ok", "cached": True, "liveCallPerformed": False, "generationId": cached.get("generationId"), "voiceoverId": cached.get("voiceoverId"), "audioDuration": cached.get("audioDuration", 0), "blockCount": len(cached.get("blocks", [])), "subtitleCount": sum(1 for sub in project.subtitles if (sub.metadata or {}).get("generationId") == cached.get("generationId")), "overallConfidence": cached.get("overallConfidence", 0), "blockRanges": cached.get("blocks", []), "warnings": cached.get("warnings", [])}
            except Exception:
                pass
    try:
        parsed = request_fish_timestamp(
            text, settings.fishApiKey, reference_id,
            model=str(data.get("model") or settings.fishModel or "s2-pro"),
            fmt=str(data.get("format") or "wav"), latency=str(data.get("latency") or "normal"),
            chunk_length=int(data.get("chunkLength", 200)), condition_on_previous_chunks=bool(data.get("conditionOnPreviousChunks", True)),
            temperature=float(data.get("temperature", 0.7)), top_p=float(data.get("topP", 0.7)),
            prosody={"speed": float(data.get("speed", 1.0)), "volume": float(data.get("volume", 0))},
        )
        return {"status": "ok", "cached": False, "liveCallPerformed": True, **materialize_structured_audio(project_id, project_dict, parsed, project_dir=_project_dir(project_id), block_ids=data.get("blockIds"), generate_subtitles=bool(data.get("generateSubtitles", True)))}
    except ValueError as exc:
        if str(exc) == "alignment_confidence_too_low":
            raise HTTPException(422, "alignment_confidence_too_low") from exc
        raise HTTPException(422, str(exc)) from exc
    except FishTimestampError as exc:
        status = exc.status_code if exc.status_code in {429, 502} else 502 if not exc.status_code else exc.status_code
        raise HTTPException(status, str(exc)) from exc
