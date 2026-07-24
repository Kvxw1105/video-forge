from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


TaskStatus = Literal["submitted", "waiting", "running", "succeeded", "failed", "cancelled"]
CapabilityName = Literal["media.probe", "video.trim", "audio.extract", "speech.asr", "video.scene_segment", "audio.source_separation", "video.subtitle_remove"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class MediaCapability(StrictModel):
    name: CapabilityName
    providerCommand: list[str] = Field(default_factory=list)
    local: bool
    asyncCapable: bool
    outputType: Literal["metadata", "video", "audio", "artifact"]
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")


class MediaExecutionRequest(StrictModel):
    capability: CapabilityName
    provider: Literal["videoforge_native", "mediakit"] | None = None
    sourceAssetId: str | None = None
    sourcePath: str | None = None
    startTime: float | None = Field(default=None, ge=0)
    endTime: float | None = Field(default=None, gt=0)
    outputName: str | None = None
    idempotencyToken: str | None = None
    privacyMode: Literal["local_only", "cloud_allowed"] = "local_only"

    @model_validator(mode="after")
    def _valid_trim(self):
        if self.capability == "video.trim":
            if self.startTime is None or self.endTime is None or self.endTime <= self.startTime:
                raise ValueError("video.trim requires endTime greater than startTime")
        return self


class MediaExecutionRecord(StrictModel):
    id: str
    status: TaskStatus
    provider: str = "videoforge_native"
    providerTaskId: str | None = None
    idempotencyToken: str
    capability: CapabilityName
    sourceAssetId: str | None = None
    sourcePath: str
    outputPath: str | None = None
    artifactId: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    providerError: dict[str, Any] | None = None
    retryable: bool = False
    cost: dict[str, Any] | None = None
    privacyMode: str = "local_only"
