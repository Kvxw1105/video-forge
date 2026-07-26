from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

from config import CONFIG_DIR


class AIImageProviderSettings(BaseModel):
    enabled: bool = False
    providerId: str = "openai-compatible"
    baseUrl: str = ""
    apiKey: str = ""
    model: str = ""
    timeoutSeconds: int = Field(default=120, ge=10, le=300)
    maxConcurrency: int = Field(default=4, ge=1, le=8)


_FILE = CONFIG_DIR / "ai_image_provider.json"


def load_ai_image_provider() -> AIImageProviderSettings:
    try:
        return AIImageProviderSettings(**json.loads(_FILE.read_text(encoding="utf-8"))) if _FILE.is_file() else AIImageProviderSettings()
    except Exception:
        return AIImageProviderSettings()


def save_ai_image_provider(settings: AIImageProviderSettings) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = _FILE.with_suffix(".tmp")
    temp.write_text(settings.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(temp, _FILE)


def public_ai_image_provider(settings: AIImageProviderSettings) -> dict:
    data = settings.model_dump()
    data["apiKeyConfigured"] = bool(data["apiKey"])
    data["apiKey"] = ""
    return data
