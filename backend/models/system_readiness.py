from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


CheckStatus = Literal["pass", "warn", "fail"]
OverallStatus = Literal["ready", "degraded", "blocked"]


class ReadinessCheck(BaseModel):
    id: str
    label: str
    status: CheckStatus
    required: bool
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ReadinessApp(BaseModel):
    name: str = "VideoForge"
    version: str = "0.1.0"
    productionMode: bool = False


class ReadinessCapabilities(BaseModel):
    projectEditing: bool
    voiceover: bool
    previewRendering: bool
    jianyingZipExport: bool
    jianyingDirectExport: bool


class ReadinessSummary(BaseModel):
    passed: int
    warnings: int
    failed: int


class ReadinessResponse(BaseModel):
    status: OverallStatus
    checkedAt: datetime
    app: ReadinessApp
    checks: list[ReadinessCheck]
    capabilities: ReadinessCapabilities
    summary: ReadinessSummary
