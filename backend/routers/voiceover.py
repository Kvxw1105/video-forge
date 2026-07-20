import uuid
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException
from services.project_service import get_project, update_project, _project_dir
from engines.voiceover import generate_voiceover, split_sentences
from routers.settings import get_tts_settings_raw

router = APIRouter(prefix="/api/projects/{project_id}/voiceover", tags=["voiceover"])
MAX_SCRIPT_CHARS = 50000


def _fmt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _generate_subtitles_from_duration(text: str, total_duration: float, font_size: int = 36, position: str = "bottom_center") -> list[dict]:
    """
    基于实际音频时长，按句子字符数比例分配字幕时间轴。
    每句末尾加 0.15s 的短间隙。
    """
    sentences = split_sentences(text)
    if not sentences:
        return []

    total_chars = sum(len(s) for s in sentences)
    if total_chars == 0:
        return []

    # 首次分配：按字符比例
    raw_times = []
    for s in sentences:
        ratio = len(s) / total_chars
        dur = max(0.5, ratio * total_duration)
        raw_times.append(dur)

    # 标准化到总时长
    raw_sum = sum(raw_times)
    if raw_sum > 0:
        raw_times = [t / raw_sum * total_duration for t in raw_times]

    # 构建字幕
    subtitles = []
    cursor = 0.0
    for i, (sentence, dur) in enumerate(zip(sentences, raw_times)):
        end = cursor + dur
        subtitles.append({
            "id": f"sub_{i+1:03d}",
            "text": sentence,
            "start": round(cursor, 3),
            "end": round(end, 3),
            "style": {"fontSize": font_size, "color": "#ffffff", "strokeColor": "#000000", "strokeWidth": 2, "position": position}
        })
        cursor = end  # 连续无间隙
    return subtitles


@router.post("")
def generate(project_id: str, data: dict):
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    text = data.get("text", "")
    if not text:
        raise HTTPException(400, "文案不能为空")

    if len(text) > MAX_SCRIPT_CHARS:
        raise HTTPException(413, f"Script exceeds the {MAX_SCRIPT_CHARS}-character limit; split it into multiple projects or sections.")

    req_engine = data.get("engine", "")
    settings = get_tts_settings_raw()
    engine = req_engine if req_engine else settings.engine
    speed = float(data.get("speed", 0) or 0)
    pitch = float(data.get("pitch", 0) or 0)
    proj_dir = _project_dir(project_id)

    # Preserve current subtitle fontSize and position from existing project
    current_font_size = 48
    current_position = "bottom_center"
    if p.subtitles:
        current_font_size = p.subtitles[0].style.get("fontSize", 48)
        current_position = p.subtitles[0].style.get("position", "bottom_center")

    # 1. 生成配音（实际时长）或纯字幕模式
    if engine == "none":
        # 纯字幕：不调 TTS，按中文语速 ~4字/秒 估算时长
        char_count = len(text.replace("\n", "").replace(" ", ""))
        actual_duration = max(3.0, char_count / 4.0)
        audio_path = None
    else:
        try:
            audio_path, actual_duration = generate_voiceover(
                text, proj_dir, engine=engine, speed=speed, pitch=pitch, settings=settings
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    # 2. 基于实际时长生成字幕
    updated_subtitles = _generate_subtitles_from_duration(text, actual_duration, current_font_size, current_position)

    # 3. 保存 SRT
    srt_lines = []
    for i, sub in enumerate(updated_subtitles, 1):
        srt_lines.append(str(i))
        srt_lines.append(f"{_fmt_time(sub['start'])} --> {_fmt_time(sub['end'])}")
        srt_lines.append(sub['text'])
        srt_lines.append("")
    srt_content = "\n".join(srt_lines)
    srt_path = proj_dir / "subtitles.srt"
    srt_path.write_text(srt_content, encoding="utf-8")

    # 4. 更新项目：追加新配音到 voiceovers 列表，并设为激活
    p_dict = p.model_dump()
    existing = list(p_dict.get("audio", {}).get("voiceovers", []))
    # 旧数据迁移：如果 voiceovers 为空但有 voiceover，先迁移
    if not existing and p_dict.get("audio", {}).get("voiceover", {}).get("file"):
        old_vo = {**p_dict["audio"]["voiceover"], "id": "vo_1", "isActive": True}
        existing = [old_vo]

    # 清理模板遗留的空配音（duration=0 且 text 空 且 file 是默认名）
    existing = [
        v for v in existing
        if not (
            float(v.get("duration", 0) or 0) <= 0
            and not v.get("text")
            and str(v.get("file") or "").replace("\\", "/").rsplit("/", 1)[-1] == "voiceover.mp3"
        )
    ]

    # 其他全部设为非激活
    for v in existing:
        v["isActive"] = False

    new_id = f"vo_{len(existing) + 1}"
    new_voiceover = {
        "id": new_id,
        "api": engine,
        "voice": engine,
        "speed": speed,
        "pitch": pitch if engine == "edge" else 0,
        "volume": 1.0,
        "file": str(audio_path) if audio_path else "",
        "duration": actual_duration,
        "text": text,
        "engine": engine,
        "isActive": True,
        "createdAt": datetime.now().isoformat(),
    }
    existing.append(new_voiceover)

    update_data = {
        "subtitles": updated_subtitles,
        "audio": {
            **p_dict.get("audio", {}),
            "voiceovers": existing,
            "voiceover": new_voiceover,  # 保持同步，兼容旧读取路径
        },
    }
    update_project(project_id, update_data)

    return {
        "audioPath": str(audio_path) if audio_path else None,
        "duration": actual_duration,
        "subtitleCount": len(updated_subtitles),
        "subtitles": updated_subtitles,
        "voiceoverId": new_id,
        "voiceovers": existing,
    }

@router.post("/switch")
def switch_voiceover(project_id: str, data: dict):
    """切换当前激活的配音，并基于该配音重新生成字幕。"""
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")

    target_id = data.get("voiceoverId", "")
    voiceovers = list(p_dict.get("audio", {}).get("voiceovers", [])) if (p_dict := p.model_dump()) else []
    if not voiceovers:
        raise HTTPException(400, "没有可用配音")

    target = next((v for v in voiceovers if v.get("id") == target_id), None)
    if not target:
        raise HTTPException(404, "配音不存在")

    # 全部设为非激活，目标设为激活
    for v in voiceovers:
        v["isActive"] = (v.get("id") == target_id)

    # 基于目标配音的文案和时长重新生成字幕
    text = target.get("text", "")
    duration = float(target.get("duration", 0))
    current_font_size = 48
    current_position = "bottom_center"
    if p.subtitles:
        current_font_size = p.subtitles[0].style.get("fontSize", 48)
        current_position = p.subtitles[0].style.get("position", "bottom_center")

    updated_subtitles = []
    if text and duration > 0:
        updated_subtitles = _generate_subtitles_from_duration(text, duration, current_font_size, current_position)
        srt_lines = []
        for i, sub in enumerate(updated_subtitles, 1):
            srt_lines.append(str(i))
            srt_lines.append(f"{_fmt_time(sub['start'])} --> {_fmt_time(sub['end'])}")
            srt_lines.append(sub["text"])
            srt_lines.append("")
        srt_path = _project_dir(project_id) / "subtitles.srt"
        srt_path.write_text("\n".join(srt_lines), encoding="utf-8")

    update_project(project_id, {
        "subtitles": updated_subtitles,
        "audio": {
            **p_dict.get("audio", {}),
            "voiceovers": voiceovers,
            "voiceover": target,
        }
    })

    return {
        "voiceoverId": target_id,
        "duration": duration,
        "subtitles": updated_subtitles,
        "subtitleCount": len(updated_subtitles),
        "voiceovers": voiceovers,
    }


@router.post("/delete")
def delete_voiceover(project_id: str, data: dict):
    """删除指定配音；如果删除的是当前激活项，激活最后一个剩余配音。"""
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")

    target_id = data.get("voiceoverId", "")
    p_dict = p.model_dump()
    voiceovers = list(p_dict.get("audio", {}).get("voiceovers", []))
    if len(voiceovers) <= 1:
        raise HTTPException(400, "至少保留一个配音")

    new_voiceovers = [v for v in voiceovers if v.get("id") != target_id]
    if len(new_voiceovers) == len(voiceovers):
        raise HTTPException(404, "配音不存在")

    # 确保有一个激活
    if not any(v.get("isActive") for v in new_voiceovers):
        new_voiceovers[-1]["isActive"] = True

    active = next((v for v in new_voiceovers if v.get("isActive")), new_voiceovers[-1])
    update_project(project_id, {
        "audio": {
            **p_dict.get("audio", {}),
            "voiceovers": new_voiceovers,
            "voiceover": active,
        }
    })

    return {
        "voiceovers": new_voiceovers,
        "activeId": active.get("id"),
    }


@router.get("/list")
def list_voiceovers(project_id: str):
    """列出项目所有配音。"""
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    p_dict = p.model_dump()
    voiceovers = list(p_dict.get("audio", {}).get("voiceovers", []))
    return {"voiceovers": voiceovers, "activeId": next((v.get("id") for v in voiceovers if v.get("isActive")), None)}
