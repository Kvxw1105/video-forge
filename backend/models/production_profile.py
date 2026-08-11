"""Thin, serialisable Director layer for autonomous video production.

Profiles intentionally contain policy only.  They never own a Project,
Timeline, Scene timing, or generated asset; the Factory compiles them into the
existing visual-generation primitives.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProductionProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    routingMode: Literal["auto", "stickman", "code_visual"] = "auto"
    preferredProviders: list[str] = Field(default_factory=list)
    fallbackOrder: list[str] = Field(default_factory=lambda: ["code_visual", "stickman"])
    candidateCount: Literal[1, 2, 4] = 1
    autoApprovalPolicy: Literal["always", "local_only", "never"] = "local_only"
    externalPolicy: Literal["local_only", "external_allowed"] = "local_only"
    codeVisualTheme: str = "cinematic, low-saturation, warm mid-century palette"
    motionPreference: Literal["static", "motion", "auto"] = "auto"
    styleAnchor: str = "cinematic, low-saturation, warm mid-century color palette"
    continuityAnchor: str = ""
    durationPolicy: Literal["exact", "crop", "loop", "speed_adjust", "reject"] = "exact"
    visualDensity: Literal["sparse", "balanced", "dense"] = "balanced"


class ProductionProfileSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str = ""
    routingMode: str
    candidateCount: int
    autoApprovalPolicy: str
    externalPolicy: str
    motionPreference: str
    visualDensity: str
