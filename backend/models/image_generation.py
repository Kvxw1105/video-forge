from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ImageGenerationChannel = Literal["builtin", "agent", "local"]
ImageGenerationRoutingMode = Literal["auto", "stickman", "code_visual"]
ImageGenerationDurationPolicy = Literal["exact", "crop", "loop", "speed_adjust", "reject"]
ImageGenerationItemStatus = Literal[
    "pending", "generating", "generated", "approved", "bound", "failed"
]
ImageGenerationBatchStatus = Literal[
    "pending",
    "running",
    "awaiting_agent",
    "awaiting_approval",
    "succeeded",
    "partial",
    "failed",
    "stale",
]


class ImageProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    providerId: str = "openai-compatible"
    baseUrl: str = ""
    apiKey: str = ""
    model: str = ""
    timeoutSeconds: int = Field(default=120, ge=10, le=300)
    maxConcurrency: int = Field(default=4, ge=1, le=8)
    maxDownloadBytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)


class ImageGenerationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidateId: str = Field(min_length=1, max_length=128)
    path: str = Field(min_length=1)
    contentHash: str = Field(min_length=64, max_length=64)
    mimeType: Literal["image/png", "image/jpeg", "image/webp", "video/mp4"]
    status: Literal["generated", "selected", "approved"] = "generated"
    revisedPrompt: str = ""
    metadata: dict = Field(default_factory=dict)
    createdAt: str


class ImageGenerationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sceneId: str = Field(min_length=1, max_length=64)
    blockId: str = Field(min_length=1, max_length=64)
    subtitleIds: list[str] = Field(min_length=1)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    duration: float = Field(gt=0)
    text: str = ""
    sceneIntent: str = ""
    subject: str = ""
    composition: str = ""
    styleAnchor: str = ""
    continuityAnchor: str = ""
    safeArea: str = ""
    prompt: str = ""
    negativePrompt: str = ""
    finalPrompt: str = Field(min_length=1)
    aspectRatio: str = "9:16"
    size: str = "1024x1536"
    inputHash: str = Field(min_length=64, max_length=64)
    expectedFilename: str = Field(min_length=1)
    status: ImageGenerationItemStatus = "pending"
    errorCode: str = ""
    error: str = ""
    attempts: int = Field(default=0, ge=0)
    candidates: list[ImageGenerationCandidate] = Field(default_factory=list)
    providerId: str = ""
    providerVersion: str = ""
    routingReason: str = ""
    routingConfidence: float = Field(default=0.0, ge=0, le=1)
    durationPolicy: ImageGenerationDurationPolicy = "exact"
    requestedMediaType: Literal["image", "video", "either"] = "image"
    outputMode: Literal["static", "video"] = "static"
    routeHints: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_timing(self):
        if self.end <= self.start:
            raise ValueError("image generation item end must be greater than start")
        if abs((self.end - self.start) - self.duration) > 0.01:
            raise ValueError("image generation item duration must match start/end")
        return self


class ImageGenerationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal[1] = 1
    batchId: str = Field(min_length=1, max_length=128)
    projectId: str = Field(min_length=1, max_length=128)
    visualPlanId: str = Field(min_length=1, max_length=64)
    visualSourceHash: str = Field(min_length=64, max_length=64)
    channel: ImageGenerationChannel
    providerId: str = ""
    model: str = ""
    size: str = ""
    candidateCount: int = Field(default=1, ge=1, le=4)
    routingMode: ImageGenerationRoutingMode = "auto"
    autoApprove: bool = False
    approvalAudit: list[dict] = Field(default_factory=list)
    status: ImageGenerationBatchStatus
    items: list[ImageGenerationItem] = Field(default_factory=list)
    createdAt: str
    updatedAt: str


class ImageBatchCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: ImageGenerationChannel = "agent"
    providerId: str = ""
    model: str = ""
    size: str = ""
    candidateCount: int = Field(default=1, ge=1, le=4)
    routingMode: ImageGenerationRoutingMode = "auto"
    autoApprove: bool = False
    styleAnchor: str = ""
    continuityAnchor: str = ""
    sceneIds: list[str] = Field(default_factory=list)
    sceneOverrides: dict[str, dict] = Field(default_factory=dict)


class ImageApprovalSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sceneId: str
    candidateId: str

