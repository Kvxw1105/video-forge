import json
import os
from pathlib import Path
from fastapi import APIRouter
import httpx
from config import DATA_DIR
from models.tts_settings import TtsSettings

router = APIRouter(prefix="/api/settings", tags=["settings"])

_SETTINGS_FILE = DATA_DIR / "tts_settings.json"
_SECRET_FIELDS = ("manboApiKey", "fishApiKey", "customApiKey")


def _load_settings() -> TtsSettings:
    if _SETTINGS_FILE.exists():
        try:
            return TtsSettings(**json.loads(_SETTINGS_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return TtsSettings()


def _save_settings(settings: TtsSettings):
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = _SETTINGS_FILE.with_name(f"{_SETTINGS_FILE.name}.tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(settings.model_dump_json(indent=2))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, _SETTINGS_FILE)
    finally:
        if temp.exists():
            temp.unlink()


def _public_settings(settings: TtsSettings) -> dict:
    data = settings.model_dump()
    for field in _SECRET_FIELDS:
        data[f"{field}Configured"] = bool(data.get(field))
        data[field] = ""
    if not data.get("fishVoicePresets"):
        data["fishVoicePresets"] = TtsSettings.model_fields["fishVoicePresets"].default_factory()
    return data


@router.get("/tts")
def get_tts_settings():
    """获取当前 TTS 配置（fishVoicePresets 缺失时填充默认值，保证 UI 始终能显示）"""
    s = _load_settings()
    return _public_settings(s)


@router.put("/tts")
def update_tts_settings(data: dict):
    """更新 TTS 配置（只更新提供的字段；如果 presets 被清空则保留默认值）"""
    current = _load_settings()
    updates = {key: value for key, value in data.items() if key in TtsSettings.model_fields}
    for field in _SECRET_FIELDS:
        if not str(updates.get(field) or "").strip():
            updates.pop(field, None)
    if "fishVoicePresets" in updates and not updates["fishVoicePresets"]:
        updates["fishVoicePresets"] = TtsSettings.model_fields["fishVoicePresets"].default_factory()
    updated = current.model_copy(update=updates)
    _save_settings(updated)
    return _public_settings(updated)


@router.post("/tts/test/fish")
def test_fish_audio():
    """从后端代理测试 Fish Audio 接口，避免前端 CORS 问题。"""
    s = _load_settings()
    if not s.fishApiKey:
        return {"ok": False, "message": "未配置 Fish Audio API Key"}
    if not s.fishReferenceId:
        return {"ok": False, "message": "未配置 Fish Audio Reference ID"}
    try:
        with httpx.Client(timeout=30) as client:
            r = client.post(
                "https://api.fish.audio/v1/tts",
                headers={
                    "Authorization": f"Bearer {s.fishApiKey}",
                    "Content-Type": "application/json",
                    "model": s.fishModel or "s2.1-pro-free",
                },
                json={
                    "text": "你好，这是 VideoForge 的 Fish Audio 接口测试。",
                    "reference_id": s.fishReferenceId,
                    "format": "mp3",
                },
            )
        content_type = (r.headers.get("content-type") or "").lower()
        if r.status_code == 200 and ("audio" in content_type or "octet-stream" in content_type):
            return {"ok": True, "message": "接口测试通过，可以生成配音"}
        try:
            err = r.json()
            return {"ok": False, "message": f"Fish Audio 返回错误: {err.get('message', r.text[:200])}"}
        except Exception:
            return {"ok": False, "message": f"Fish Audio 测试失败: HTTP {r.status_code} {r.text[:200]}"}
    except httpx.HTTPError as e:
        return {"ok": False, "message": f"网络错误: {e}"}
    except Exception as e:
        return {"ok": False, "message": f"测试失败: {e}"}


@router.post("/tts/test/manbo")
def test_manbo():
    """从后端代理测试曼波 VIP 接口，避免前端 CORS 问题。"""
    s = _load_settings()
    if not s.manboApiKey:
        return {"ok": False, "message": "未配置曼波 API Key"}
    url = s.manboApiUrl or "https://api.milorapart.top/apis/mbAIscvip"
    try:
        with httpx.Client(timeout=30) as client:
            r = client.get(
                url,
                params={"text": "你好，这是 VideoForge 的曼波接口测试。", "key": s.manboApiKey, "speed": "0", "format": "mp3"},
                headers={"Authorization": f"Bearer {s.manboApiKey}"},
            )
        content_type = (r.headers.get("content-type") or "").lower()
        # 曼波接口直接返回 mp3 音频流
        if r.status_code == 200 and ("audio" in content_type or "octet-stream" in content_type or len(r.content) > 1000):
            return {"ok": True, "message": "接口测试通过，可以生成配音"}
        try:
            err = r.json()
            return {"ok": False, "message": f"曼波接口返回错误: {err.get('message', r.text[:200])}"}
        except Exception:
            return {"ok": False, "message": f"曼波接口测试失败: HTTP {r.status_code} {r.text[:200]}"}
    except httpx.HTTPError as e:
        return {"ok": False, "message": f"网络错误: {e}"}
    except Exception as e:
        return {"ok": False, "message": f"测试失败: {e}"}


# 供其他模块导入使用
def get_tts_settings_raw() -> TtsSettings:
    return _load_settings()
