"""Strict Agent Video Factory contracts layered on the durable batch spec."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class VisualWorkflow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    mode: Literal["pre_supplied", "generation_pack", "none"] = "generation_pack"
    planningMode: Literal["fixed_units", "target_duration", "agent_explicit", "hybrid"] = "hybrid"
    targetDuration: float = Field(default=7, gt=0)
    minDuration: float = Field(default=4, gt=0)
    maxDuration: float = Field(default=12, gt=0)
    defaultMediaType: Literal["image", "video", "either"] = "image"
    requireCompleteCoverage: bool = True
    missingScenePolicy: Literal["black", "reuse_previous"] = "black"


FACTORY_ITEM_PHASES = {"validating", "creating_project", "generating_voiceover", "aligning_subtitles", "planning_visual_scenes", "exporting_generation_pack", "awaiting_visual_assets", "importing_visual_assets", "validating_visual_coverage", "rendering_preview", "exporting_jianying", "done", "failed"}
FACTORY_BATCH_STATUSES = {"queued", "running", "awaiting_visual_assets", "ready_to_resume", "succeeded", "partial", "failed", "interrupted", "cancelled"}
