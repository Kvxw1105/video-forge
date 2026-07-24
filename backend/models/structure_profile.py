"""Versioned, user-configurable structural rules for narrative video scripts."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


STRUCTURE_BLOCK_TYPES = (
    "HOOK", "CTA_TAG", "PROBLEM", "STORY", "MECHANISM", "JUDGMENT",
    "METHOD", "SHORT_OUTRO", "BRIDGE_IN", "BRIDGE_OUT", "COMMENT_CTA",
)


class VisualPolicy(BaseModel):
    """Default visual direction. It deliberately contains no clock values."""

    model_config = ConfigDict(extra="forbid")

    style: Literal[
        "black_screen_text", "color_card", "cinematic_images", "diagram_or_steps", "mixed"
    ] = "mixed"
    scenePolicy: Literal[
        "single_clip", "split_by_semantic_cluster", "one_scene_per_step", "auto"
    ] = "auto"
    notes: str = Field(default="", max_length=500)


class StructureBlockRule(BaseModel):
    """A semantic block expected by a profile, before voice alignment exists."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")
    type: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=80)
    required: bool = True
    targetChars: int | None = Field(default=None, ge=1, le=20_000)
    guidance: str = Field(default="", max_length=2_000)
    visualPolicy: VisualPolicy = Field(default_factory=VisualPolicy)

    @field_validator("type")
    @classmethod
    def _canonical_block_type(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in STRUCTURE_BLOCK_TYPES:
            raise ValueError(f"unsupported structure block type: {value}")
        return normalized


class StructureProfile(BaseModel):
    """Reusable authoring profile. User-owned copies are stored outside the repo."""

    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal[1] = 1
    id: str = Field(default="", max_length=96, pattern=r"^(|[A-Za-z0-9_-]+)$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1_000)
    version: int = Field(default=1, ge=1)
    builtin: bool = False
    blocks: list[StructureBlockRule] = Field(min_length=1, max_length=30)
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _unique_rule_ids(self):
        rule_ids = [rule.id for rule in self.blocks]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("structure profile block rule ids must be unique")
        return self


class StructureProfileSnapshot(BaseModel):
    """Immutable profile state attached to a project at authoring time."""

    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal[1] = 1
    profileId: str = Field(min_length=1, max_length=96, pattern=r"^[A-Za-z0-9_-]+$")
    profileVersion: int = Field(ge=1)
    capturedAt: str = Field(min_length=1)
    profile: StructureProfile

    @model_validator(mode="after")
    def _matches_embedded_profile(self):
        if self.profile.id != self.profileId:
            raise ValueError("profile snapshot id must match embedded profile")
        if self.profile.version != self.profileVersion:
            raise ValueError("profile snapshot version must match embedded profile")
        return self


def snapshot_profile(profile: StructureProfile) -> StructureProfileSnapshot:
    """Copy a profile into a project-safe, immutable payload."""

    copied = StructureProfile.model_validate(deepcopy(profile.model_dump()))
    return StructureProfileSnapshot(
        profileId=copied.id,
        profileVersion=copied.version,
        capturedAt=datetime.now(timezone.utc).isoformat(),
        profile=copied,
    )
