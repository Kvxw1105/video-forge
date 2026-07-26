from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SubjectSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["person", "pair", "group", "system", "animal"] = "person"
    count: int = Field(default=1, ge=0, le=8)
    role: str = "protagonist"


class SymbolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    role: Literal["primary", "secondary", "environment"] = "primary"


class SceneConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subtitle_safe_zone: Literal["bottom_24", "bottom_30", "none"] = "bottom_24"
    transparent_background: bool = True


class SemanticSceneGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    scene_id: str = Field(min_length=1)
    order: int = Field(ge=1)
    block_id: str | None = None
    subtitle_ids: list[str] = Field(default_factory=list)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(min_length=1)
    subject: SubjectSpec = Field(default_factory=SubjectSpec)
    desire: str | None = None
    opposing_force: str | None = None
    action: str | None = None
    cost: str | None = None
    turning_point: str | None = None
    topic: str | None = None
    emotion: str | None = None
    visual_family: Literal[
        "control", "anxiety", "people_pleasing", "evidence",
        "awakening", "hidden_path", "trap_detection"
    ]
    composition_family: str
    complexity: Literal["A", "B", "C"] = "B"
    ip_pack: Literal["neutral", "xuanqi", "huicewolf", "ayin"] = "neutral"
    preferred_renderer: str | None = None
    motion_profile: Literal[
        "control", "anxiety", "people_pleasing", "evidence",
        "awakening", "hidden_path", "trap_detection"
    ]
    symbols: list[SymbolSpec] = Field(default_factory=list)
    constraints: SceneConstraints = Field(default_factory=SceneConstraints)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_times(self) -> "SemanticSceneGraph":
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class PaletteSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    background: str
    foreground: str
    secondary: str
    accent: str
    muted: str


class StrokeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    primary: float = Field(default=14, ge=4, le=36)
    secondary: float = Field(default=9, ge=2, le=24)
    detail: float = Field(default=5, ge=1, le=16)


class StyleContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    style_id: str
    renderer_id: Literal["white_sketch", "silhouette", "pixel_rules", "mechanism_diagram"]
    theme_mode: Literal["dark", "light"]
    width: int = 1080
    height: int = 1920
    palette: PaletteSpec
    stroke: StrokeSpec = Field(default_factory=StrokeSpec)
    negative_space: Literal["medium", "high"] = "high"
    subtitle_safe_zone: Literal["bottom_24", "bottom_30", "none"] = "bottom_24"
    ip_pack: Literal["neutral", "xuanqi", "huicewolf", "ayin"] = "neutral"
    seed: int = 0
    renderer_options: dict[str, Any] = Field(default_factory=dict)


class MotionInstruction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_id: str
    property: Literal["x", "y", "scale", "rotation", "opacity", "stroke", "visibility"]
    start_time: float
    end_time: float
    from_value: float | int | bool
    to_value: float | int | bool
    easing: str = "easeInOutCubic"


class MotionBeat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    time: float
    type: str


class MotionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    profile: str
    theme_mode: Literal["dark", "light"]
    duration: float
    actor_motions: list[MotionInstruction] = Field(default_factory=list)
    symbol_motions: list[MotionInstruction] = Field(default_factory=list)
    environment_motions: list[MotionInstruction] = Field(default_factory=list)
    camera_motions: list[MotionInstruction] = Field(default_factory=list)
    beats: list[MotionBeat] = Field(default_factory=list)
    deterministic: Literal[True] = True
    seed: int = 0


class RenderedAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["svg", "png"]
    path: str
    sha256: str
    width: int
    height: int
    transparent: bool = True


class CandidateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str
    renderer_id: str
    renderer_version: str
    theme_mode: Literal["dark", "light"]
    scene_id: str
    visual_family: str
    template_id: str
    assets: list[RenderedAsset]
    motion_plan: MotionPlan
    layer_ids: list[str]
    status: Literal["generated", "failed"] = "generated"
    warnings: list[str] = Field(default_factory=list)


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[3] = 3
    project_id: str
    provider: str = "semantic_visual_renderer_suite"
    provider_version: str = "0.5.0"
    scenes: list[SemanticSceneGraph]
    styles: list[StyleContract]
    candidates: list[CandidateRecord]
    stats: dict[str, Any]
