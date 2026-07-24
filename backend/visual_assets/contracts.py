from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


ERROR_CODES = {
    "invalid_request",
    "unsupported_source_mode",
    "invalid_segment_time",
    "duplicate_segment_id",
    "visual_source_missing",
    "semantic_low_confidence",
    "stickman_template_not_found",
    "invalid_template_parameters",
    "svg_render_failed",
    "svg_validation_failed",
    "png_converter_unavailable",
    "png_render_failed",
    "png_alpha_invalid",
    "output_conflict",
    "manual_override_protected",
    "contact_sheet_failed",
    "partial_generation",
}

ItemStatus = Literal["pending", "generated", "skipped_unchanged", "fallback", "needs_review", "manual_override", "failed"]
RunStatus = Literal["planned", "routing", "rendering_svg", "converting_png", "generating_contact_sheet", "succeeded", "partial", "failed", "interrupted"]


class VisualSemantic(StrictModel):
    topic: str | None = None
    emotion: str | None = None
    actors: int = Field(default=1, ge=1, le=8)
    visualIntent: str | None = None
    templateId: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VisualAssetSourceItem(StrictModel):
    id: str = Field(min_length=1, max_length=96)
    order: int = Field(ge=1)
    blockId: str | None = None
    subtitleIds: list[str] = Field(default_factory=list)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(min_length=1)
    semantic: VisualSemantic = Field(default_factory=VisualSemantic)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("subtitleIds")
    @classmethod
    def _unique_subtitles(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)) or any(not item for item in value):
            raise ValueError("subtitleIds must be unique non-empty strings")
        return value

    @model_validator(mode="after")
    def _valid_time(self):
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class VisualAssetSource(StrictModel):
    mode: Literal["inline_segments", "subtitles", "visual_plan_snapshot"]
    visualPlanId: str | None = None
    visualSourceHash: str | None = None
    segments: list[VisualAssetSourceItem] = Field(default_factory=list)
    subtitles: list[dict[str, Any]] = Field(default_factory=list)
    visualPlan: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _validate_source(self):
        if self.mode == "inline_segments" and not self.segments:
            raise ValueError("inline_segments requires segments")
        if self.mode == "subtitles" and not self.subtitles:
            raise ValueError("subtitles requires subtitles")
        if self.mode == "visual_plan_snapshot" and not self.visualPlan:
            raise ValueError("visual_plan_snapshot requires visualPlan")
        ids = [item.id for item in self.segments]
        orders = [item.order for item in self.segments]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate segment id")
        if len(orders) != len(set(orders)):
            raise ValueError("duplicate order")
        return self


class RoutingOptions(StrictModel):
    mode: Literal["structured_first"] = "structured_first"
    allowLlm: bool = False
    minimumConfidence: float = Field(default=0.65, ge=0, le=1)
    lowConfidencePolicy: Literal["needs_review", "fallback"] = "needs_review"
    generateAlternatives: int = Field(default=0, ge=0, le=3)


class RenderCanvas(StrictModel):
    width: int = Field(default=1080, ge=64, le=4096)
    height: int = Field(default=1920, ge=64, le=4096)


class StickmanTheme(StrictModel):
    foreground: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$")
    accent: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    lineWidth: int = Field(default=12, ge=1, le=80)
    lineCap: Literal["round", "butt", "square"] = "round"
    lineJoin: Literal["round", "miter", "bevel"] = "round"


class RenderConfig(StrictModel):
    provider: Literal["stickman_svg"] = "stickman_svg"
    providerVersion: str = "0.1.0"
    seed: int = 0
    canvas: RenderCanvas = Field(default_factory=RenderCanvas)
    theme: StickmanTheme = Field(default_factory=StickmanTheme)
    rendererVersion: str = "0.1.0"


class ExportOptions(StrictModel):
    svg: bool = True
    png: bool = False
    manifest: bool = True
    contactSheet: bool = True
    generationReport: bool = True


class GenerationBehavior(StrictModel):
    existingOutputPolicy: Literal["skip_unchanged", "regenerate", "fail_on_existing"] = "skip_unchanged"
    protectManualEdits: bool = True
    replaceManualEdits: bool = False
    segmentId: str | None = None


class VisualAssetRenderRequest(StrictModel):
    schemaVersion: Literal[1] = 1
    projectId: str = Field(min_length=1)
    source: VisualAssetSource
    routing: RoutingOptions = Field(default_factory=RoutingOptions)
    renderer: RenderConfig = Field(default_factory=RenderConfig)
    exports: ExportOptions = Field(default_factory=ExportOptions)
    behavior: GenerationBehavior = Field(default_factory=GenerationBehavior)


class VisualAssetRoute(StrictModel):
    templateId: str
    templateVersion: str
    confidence: float = Field(ge=0, le=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    fallbackUsed: bool = False
    needsReview: bool = False
    reason: str = ""


class RenderedSvg(StrictModel):
    svg: str
    templateId: str
    templateVersion: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    composition: dict[str, Any] = Field(default_factory=dict)
    motionHint: dict[str, Any] = Field(default_factory=dict)


class GenerationError(StrictModel):
    code: str
    message: str
    segmentId: str | None = None
    templateId: str | None = None
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("code")
    @classmethod
    def _known(cls, value: str) -> str:
        if value not in ERROR_CODES:
            raise ValueError(f"unknown error code: {value}")
        return value


class VisualAssetManifestItem(StrictModel):
    segmentId: str
    order: int
    blockId: str | None = None
    subtitleIds: list[str] = Field(default_factory=list)
    start: float
    end: float
    duration: float
    text: str
    semantic: dict[str, Any] = Field(default_factory=dict)
    templateId: str
    templateVersion: str
    confidence: float = Field(ge=0, le=1)
    templateParameters: dict[str, Any] = Field(default_factory=dict)
    svgPath: str | None = None
    pngPath: str | None = None
    svgSha256: str | None = None
    pngSha256: str | None = None
    composition: dict[str, Any] = Field(default_factory=dict)
    motionHint: dict[str, Any] = Field(default_factory=dict)
    inputHash: str
    status: ItemStatus
    fallbackUsed: bool = False
    manualOverride: bool = False
    warnings: list[str] = Field(default_factory=list)
    error: GenerationError | None = None


class VisualAssetManifest(StrictModel):
    schemaVersion: Literal[1] = 1
    projectId: str
    provider: str
    providerVersion: str
    visualPlanId: str | None = None
    visualSourceHash: str | None = None
    inputHash: str
    items: list[VisualAssetManifestItem] = Field(default_factory=list)


class GenerationReport(StrictModel):
    schemaVersion: Literal[1] = 1
    projectId: str
    provider: str
    providerVersion: str
    status: RunStatus
    itemCount: int = 0
    generatedCount: int = 0
    skippedCount: int = 0
    manualOverrideCount: int = 0
    failedCount: int = 0
    pngStatus: Literal["not_requested", "succeeded", "unavailable", "failed"] = "not_requested"
    errors: list[GenerationError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rasterizer: dict[str, Any] = Field(default_factory=dict)


class VisualAssetGenerationResult(StrictModel):
    schemaVersion: Literal[1] = 1
    runId: str
    projectId: str
    visualPlanId: str | None = None
    visualSourceHash: str | None = None
    inputHash: str
    provider: str
    providerVersion: str
    status: RunStatus
    manifestPath: str | None = None
    contactSheetPath: str | None = None
    contactSheetPngPath: str | None = None
    generationReportPath: str | None = None
    items: list[VisualAssetManifestItem] = Field(default_factory=list)
    errors: list[GenerationError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def normalize_inline_segments(segments: list[dict[str, Any]]) -> list[VisualAssetSourceItem]:
    return [VisualAssetSourceItem.model_validate(item) for item in segments]


def normalize_subtitles(subtitles: list[dict[str, Any]]) -> list[VisualAssetSourceItem]:
    ordered = sorted(subtitles, key=lambda item: (float(item.get("start", 0)), str(item.get("id", ""))))
    return [
        VisualAssetSourceItem(
            id=str(item.get("id") or f"subtitle_{index:03d}"),
            order=index,
            blockId=str((item.get("metadata") or {}).get("blockId") or "") or None,
            subtitleIds=[str(item.get("id") or f"subtitle_{index:03d}")],
            start=float(item.get("start", 0)),
            end=float(item.get("end", 0)),
            text=str(item.get("text") or ""),
            semantic=VisualSemantic.model_validate((item.get("metadata") or {}).get("semantic") or {}),
        )
        for index, item in enumerate(ordered, 1)
    ]


def normalize_visual_plan_snapshot(project_dict: dict[str, Any]) -> list[VisualAssetSourceItem]:
    plan = (((project_dict.get("structuredContent") or {}).get("episode") or {}).get("visualPlan") or {})
    subtitles = {item.get("id"): item for item in project_dict.get("subtitles") or []}
    items = []
    for order, scene in enumerate(plan.get("scenes") or [], 1):
        ids = list(scene.get("subtitleIds") or [])
        selected = [subtitles[item] for item in ids if item in subtitles]
        start = float(selected[0].get("start", 0)) if selected else 0.0
        end = float(selected[-1].get("end", start + 1.0)) if selected else start + 1.0
        text = "".join(str(item.get("text") or "") for item in selected) or str(scene.get("summary") or scene.get("prompt") or scene.get("id"))
        items.append(VisualAssetSourceItem(
            id=str(scene.get("id")),
            order=order,
            blockId=str(scene.get("blockId") or "") or None,
            subtitleIds=ids,
            start=start,
            end=end,
            text=text,
            semantic=VisualSemantic.model_validate((scene.get("metadata") or {}).get("semantic") or {}),
            metadata={"visualScene": scene},
        ))
    return items
