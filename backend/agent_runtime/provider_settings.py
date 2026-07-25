from __future__ import annotations

import json
import os
from pathlib import Path
from pydantic import BaseModel, Field
from config import CONFIG_DIR


class AgentProviderSettings(BaseModel):
    enabled: bool = False
    providerId: str = "custom"
    baseUrl: str = ""
    apiType: str = "openai-completions"
    apiKey: str = ""
    model: str = ""
    timeoutSeconds: int = Field(default=30, ge=5, le=120)


_FILE = CONFIG_DIR / "agent_provider.json"


def load_agent_provider() -> AgentProviderSettings:
    try:
        return AgentProviderSettings(**json.loads(_FILE.read_text(encoding="utf-8"))) if _FILE.is_file() else AgentProviderSettings()
    except Exception:
        return AgentProviderSettings()


def save_agent_provider(settings: AgentProviderSettings) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = _FILE.with_suffix(".tmp")
    temp.write_text(settings.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(temp, _FILE)


def public_agent_provider(settings: AgentProviderSettings) -> dict:
    data = settings.model_dump()
    data["apiKeyConfigured"] = bool(data["apiKey"])
    data["apiKey"] = ""
    return data
