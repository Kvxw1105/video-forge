"""Audio analysis router — analyze BGM for beat/energy/onset data."""

from fastapi import APIRouter, HTTPException
from services.project_service import get_project, _project_dir
from engines.audio_analyzer import analyze_audio, generate_cue_points

router = APIRouter(tags=["audio-analysis"])


@router.get("/api/projects/{project_id}/analyze-bgm")
def analyze_project_bgm(project_id: str):
    """分析项目 BGM 的音频特征（BPM、节拍、能量、段落）"""
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")

    proj_dir = _project_dir(project_id)

    # 支持多 BGM 轨道：分析第一首
    bgm_tracks = p.audio.bgm.tracks
    if not bgm_tracks and p.audio.bgm.file:
        # 兼容旧数据
        bgm_path = proj_dir / p.audio.bgm.file
    elif bgm_tracks:
        bgm_path = proj_dir / bgm_tracks[0].file
    else:
        raise HTTPException(400, "项目没有 BGM")

    if not bgm_path.exists():
        raise HTTPException(404, f"BGM 文件不存在: {bgm_path}")

    try:
        analysis = analyze_audio(str(bgm_path))
    except Exception as e:
        raise HTTPException(500, f"音频分析失败: {str(e)}")

    return {"status": "ok", "analysis": analysis}


@router.post("/api/projects/{project_id}/cue-points")
def get_cue_points(project_id: str, mode: str = "beat", image_count: int = 10):
    """根据音频分析生成卡点时间表"""
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")

    proj_dir = _project_dir(project_id)
    bgm_tracks = p.audio.bgm.tracks
    if not bgm_tracks and p.audio.bgm.file:
        bgm_path = proj_dir / p.audio.bgm.file
    elif bgm_tracks:
        bgm_path = proj_dir / bgm_tracks[0].file
    else:
        raise HTTPException(400, "项目没有 BGM")

    if not bgm_path.exists():
        raise HTTPException(404, f"BGM 文件不存在: {bgm_path}")

    try:
        analysis = analyze_audio(str(bgm_path))
        cue_points = generate_cue_points(analysis, image_count, mode)
    except Exception as e:
        raise HTTPException(500, f"卡点计算失败: {str(e)}")

    return {
        "status": "ok",
        "bpm": analysis["bpm"],
        "duration": analysis["duration"],
        "mode": mode,
        "cue_points": cue_points,
        "analysis": analysis,
    }
