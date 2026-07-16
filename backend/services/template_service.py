"""Template service — CRUD for project templates."""
from copy import deepcopy
import json
import uuid
from pathlib import Path
from datetime import datetime

TEMPLATES_DIR = Path(__file__).parent.parent / "projects" / "templates"

# Built-in templates
BUILTIN_TEMPLATES = [
    {
        "id": "tpl_single_voiceover",
        "name": "单图贯穿旁白",
        "description": "一张图 + 旁白配音 + 字幕，最基础的短视频模板",
        "builtin": True,
        "templateId": "single_image_voiceover",
        "visualMode": "single",
        "canvas": {"ratio": "9:16", "width": 1080, "height": 1920, "fps": 30,
                   "background": {"type": "color", "value": "#000000"}},
        "overlays": {"subtitle_enabled": True,
                     "title": {"text": "", "position": "top_center", "fontSize": 48,
                               "color": "#ffffff", "enabled": False},
                     "watermark": {"text": "", "position": "top_right", "fontSize": 24,
                                   "color": "#ffffff80", "enabled": False}},
        "audio": {"voiceover": {"api": "manbo_vip", "voice": "manbo", "speed": 0, "file": ""},
                  "bgm": {"file": "", "volume": 0.3, "loop": True, "fadeIn": 0.0, "fadeOut": 2.0}},
    },
    {
        "id": "tpl_carousel",
        "name": "图片轮播",
        "description": "多张图片自动轮播 + 配音，适合混剪空镜",
        "builtin": True,
        "templateId": "image_carousel",
        "visualMode": "carousel",
        "canvas": {"ratio": "9:16", "width": 1080, "height": 1920, "fps": 30,
                   "background": {"type": "color", "value": "#000000"}},
        "overlays": {"subtitle_enabled": True,
                     "title": {"text": "", "position": "top_center", "fontSize": 48,
                               "color": "#ffffff", "enabled": False},
                     "watermark": {"text": "", "position": "top_right", "fontSize": 24,
                                   "color": "#ffffff80", "enabled": False}},
        "audio": {"voiceover": {"api": "manbo_vip", "voice": "manbo", "speed": 0, "file": ""},
                  "bgm": {"file": "", "volume": 0.3, "loop": True, "fadeIn": 0.0, "fadeOut": 2.0}},
    },
    {
        "id": "tpl_widescreen",
        "name": "横屏 16:9",
        "description": "横屏视频模板，适合 B站/YouTube",
        "builtin": True,
        "templateId": "widescreen_single_image",
        "visualMode": "single",
        "canvas": {"ratio": "16:9", "width": 1920, "height": 1080, "fps": 30,
                   "background": {"type": "color", "value": "#000000"}},
        "overlays": {"subtitle_enabled": True,
                     "title": {"text": "", "position": "top_center", "fontSize": 48,
                               "color": "#ffffff", "enabled": False},
                     "watermark": {"text": "", "position": "top_right", "fontSize": 24,
                                   "color": "#ffffff80", "enabled": False}},
        "audio": {"voiceover": {"api": "manbo_vip", "voice": "manbo", "speed": 0, "file": ""},
                  "bgm": {"file": "", "volume": 0.3, "loop": True, "fadeIn": 0.0, "fadeOut": 2.0}},
    },
]


def _ensure_dir():
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def list_templates() -> list[dict]:
    """Return all templates (built-in + user-saved)."""
    _ensure_dir()
    result = [_sanitize_template(t) for t in BUILTIN_TEMPLATES]
    for f in TEMPLATES_DIR.glob("*.json"):
        try:
            t = json.loads(f.read_text(encoding="utf-8"))
            result.append(_sanitize_template(t))
        except Exception:
            pass
    return result


def get_template(template_id: str) -> dict | None:
    for t in BUILTIN_TEMPLATES:
        if t["id"] == template_id:
            return _sanitize_template(t)
    _ensure_dir()
    tpl_file = TEMPLATES_DIR / f"{template_id}.json"
    if tpl_file.exists():
        return _sanitize_template(json.loads(tpl_file.read_text(encoding="utf-8")))
    return None


def save_template(data: dict) -> dict:
    """Save a user template from project data."""
    _ensure_dir()
    tpl_id = f"tpl_{uuid.uuid4().hex[:8]}"
    tpl = {
        "id": tpl_id,
        "name": data.get("name", "未命名模板"),
        "description": data.get("description", ""),
        "builtin": False,
        "templateId": data.get("templateId", "single_image_voiceover"),
        "visualMode": data.get("visualMode", "single"),
        "canvas": data.get("canvas", {}),
        "overlays": data.get("overlays", {}),
        "audio": data.get("audio", {}),
        "timeline": data.get("timeline", {"voiceoverStartAt": 0, "blocks": []}),
        "perImageDuration": data.get("perImageDuration", 1.0),
        "shuffleMode": data.get("shuffleMode", data.get("visualMode") == "carousel"),
        "created_at": datetime.now().isoformat(),
    }
    tpl = _sanitize_template(tpl)
    tpl_file = TEMPLATES_DIR / f"{tpl_id}.json"
    tpl_file.write_text(json.dumps(tpl, indent=2, ensure_ascii=False), encoding="utf-8")
    return tpl


def delete_template(template_id: str) -> bool:
    if template_id.startswith("tpl_") and any(t["id"] == template_id for t in BUILTIN_TEMPLATES):
        return False  # can't delete built-in
    _ensure_dir()
    tpl_file = TEMPLATES_DIR / f"{template_id}.json"
    if tpl_file.exists():
        tpl_file.unlink()
        return True
    return False


def _sanitize_template(template: dict) -> dict:
    if not isinstance(template, dict):
        return template
    reusable_keys = {
        "id", "name", "description", "builtin", "templateId", "visualMode",
        "canvas", "overlays", "audio", "timeline", "perImageDuration",
        "shuffleMode", "created_at",
    }
    tpl = {key: deepcopy(value) for key, value in template.items() if key in reusable_keys}

    audio = tpl.get("audio") if isinstance(tpl.get("audio"), dict) else {}
    voiceover = audio.get("voiceover") if isinstance(audio.get("voiceover"), dict) else {}
    bgm = audio.get("bgm") if isinstance(audio.get("bgm"), dict) else {}
    tpl["audio"] = {
        "voiceover": {
            key: deepcopy(voiceover[key])
            for key in ("api", "voice", "speed", "pitch", "volume")
            if key in voiceover
        },
        "voiceovers": [],
        "bgm": {
            key: deepcopy(bgm[key])
            for key in ("volume", "loop", "fadeIn", "fadeOut")
            if key in bgm
        },
        "sfx": [],
    }
    return tpl
