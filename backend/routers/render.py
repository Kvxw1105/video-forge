from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from services.project_service import get_project, _project_dir, resolve_project_paths
from services.jobs import start_job
from engines.renderer import render_preview
from engines.audio_analyzer import analyze_audio, generate_cue_points
from shared.voiceover import select_active_voiceover
from shared.media_probe import probe_media_duration
from shared.structured_content import compile_structured_media_variant
from shared.timeline_compiler import compile_project_timeline

router = APIRouter(tags=["render"])


@router.post("/api/projects/{project_id}/preview")
def generate_preview(project_id: str, cue_mode: str | None = None):
    """Generate a preview MP4 video for the project.

    If cue_mode is beat/onset/energy/section/uniform and BGM exists, cue points drive
    segment timing. If analysis fails, render still proceeds with existing timing.
    """
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")

    proj_dict = p.model_dump()
    proj_dir = _project_dir(project_id)
    output_path = proj_dir / "preview.mp4"
    proj_dict = resolve_project_paths(proj_dir, proj_dict)
    _require_active_voiceover(proj_dict)

    cue_points = None
    if cue_mode and cue_mode != "uniform":
        cue_points = _safe_cue_points(proj_dict, len(proj_dict.get("segments", [])), cue_mode)

    try:
        output_path.unlink(missing_ok=True)
        render_preview(proj_dict, output_path, cue_points=cue_points)
    except Exception as e:
        output_path.unlink(missing_ok=True)
        raise HTTPException(500, f"预览渲染失败: {str(e)}")

    if not output_path.exists() or output_path.stat().st_size == 0:
        output_path.unlink(missing_ok=True)
        raise HTTPException(500, "预览渲染失败，输出文件不存在")
    version = int(output_path.stat().st_mtime_ns)

    return {
        "status": "ok",
        "previewUrl": f"/api/projects/{project_id}/assets/project-file/preview.mp4?v={version}",
        "duration": _get_mp4_duration(output_path),
    }


@router.post("/api/projects/{project_id}/structured/variants/{variant_id}/preview")
def generate_structured_variant_preview(project_id: str, variant_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    if p.structuredContent is None:
        raise HTTPException(409, "Project does not contain structuredContent")
    try:
        project_view = resolve_project_paths(_project_dir(project_id), p.model_dump())
        compiled_variant = compile_structured_media_variant(project_view, variant_id)
        _require_active_voiceover(project_view)
        output_path = _project_dir(project_id) / f"preview_{variant_id}.mp4"
        output_path.unlink(missing_ok=True)
        render_preview(project_view, output_path)
        timeline = compile_project_timeline(project_view, duration_resolver=probe_media_duration)
        return {
            "status": "ok", "variantId": variant_id,
            "previewUrl": f"/api/projects/{project_id}/assets/project-file/{output_path.name}",
            "duration": timeline.total_duration,
            "blockCount": len(compiled_variant.block_windows),
            "voiceoverClipCount": len(timeline.voiceover_clips),
            "visualClipCount": len(timeline.visual_clips),
            "subtitleCount": len(timeline.subtitles),
            "warnings": list(dict.fromkeys((*compiled_variant.warnings, *timeline.warnings))),
        }
    except KeyError as e:
        raise HTTPException(404, f"Variant not found: {variant_id}") from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Structured variant preview failed: {e}") from e


@router.post("/api/projects/{project_id}/preview/start")
def start_generate_preview(project_id: str, cue_mode: str | None = None):
    def work(update):
        update(8, "validate", "检查项目")
        update(24, "render", "渲染预览")
        result = generate_preview(project_id, cue_mode)
        update(92, "probe", "读取预览信息")
        return result

    return start_job("preview", work)


def _require_active_voiceover(project: dict):
    audio = project.get("audio", {}) if isinstance(project, dict) else {}
    structured_segments = audio.get("voiceoverSegments") or []
    if structured_segments and any(str(item.get("file") or "") for item in structured_segments):
        return
    active = select_active_voiceover(audio)
    file_path = active.get("file", "") if isinstance(active, dict) else ""
    if not file_path:
        raise HTTPException(400, "请先生成配音后再预览/导出")
    if not Path(file_path).exists():
        raise HTTPException(400, f"配音文件不存在: {Path(file_path).name}")


def _safe_cue_points(project: dict, image_count: int, mode: str):
    if image_count <= 0:
        return None
    bgm_path = ""
    bgm = project.get("audio", {}).get("bgm", {})
    tracks = bgm.get("tracks") or []
    if tracks:
        bgm_path = tracks[0].get("file", "")
    elif bgm.get("file"):
        bgm_path = bgm.get("file", "")
    if not bgm_path or not Path(bgm_path).exists():
        return None
    try:
        analysis = analyze_audio(bgm_path)
        return generate_cue_points(analysis, image_count, mode)
    except Exception:
        return None


def _get_mp4_duration(path: Path) -> float:
    return probe_media_duration(path)
