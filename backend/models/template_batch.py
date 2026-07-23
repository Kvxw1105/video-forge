"""Strict request models for durable template batch production."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SAFE_KEY = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class BatchVoiceover(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    engine: Literal["none", "edge", "manbo", "custom", "fish_audio"] = "edge"
    speed: float = 0
    generateSubtitles: bool = True


class BatchOutputs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview: bool = True
    jianyingDirect: bool = False
    jianyingZip: bool = False


class BatchDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ratio: Literal["9:16", "16:9", "1:1", "4:5", "4:3"] = "9:16"
    inputMode: Literal["plain_script", "structured_markdown"] = "plain_script"
    voiceover: BatchVoiceover = Field(default_factory=BatchVoiceover)
    outputs: BatchOutputs = Field(default_factory=BatchOutputs)
    continueOnError: bool = True
    maxRetries: int = Field(default=0, ge=0, le=2)
    concurrency: int = Field(default=1, ge=1, le=2)


class BatchAssets(BaseModel):
    model_config = ConfigDict(extra="forbid")
    images: list[str] = Field(default_factory=list, max_length=100)
    videos: list[str] = Field(default_factory=list, max_length=100)
    bgm: str | None = None


class BatchVisualAssets(BaseModel):
    model_config = ConfigDict(extra="forbid")
    folder: str | None = None
    manifest: dict[str, str] | None = None


class TemplateBatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    itemId: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    script: str | None = None
    structuredMarkdown: str | None = None
    templateId: str | None = None
    variables: dict[str, str] = Field(default_factory=dict)
    assets: BatchAssets = Field(default_factory=BatchAssets)
    overrides: dict = Field(default_factory=dict)
    outputs: BatchOutputs | None = None
    visualAssets: BatchVisualAssets | None = None

    @field_validator("itemId")
    @classmethod
    def _safe_item_id(cls, value: str) -> str:
        if not SAFE_KEY.fullmatch(value):
            raise ValueError("itemId must use only letters, numbers, _ and -")
        return value


class TemplateBatchSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal[1] = 1
    name: str = Field(min_length=1, max_length=200)
    idempotencyKey: str = Field(min_length=1, max_length=128)
    templateId: str | None = None
    defaults: BatchDefaults = Field(default_factory=BatchDefaults)
    items: list[TemplateBatchItem] = Field(min_length=1, max_length=500)
    visualWorkflow: dict | None = None

    @field_validator("idempotencyKey")
    @classmethod
    def _safe_key(cls, value: str) -> str:
        if not SAFE_KEY.fullmatch(value):
            raise ValueError("idempotencyKey must use only letters, numbers, _ and -")
        return value

    @model_validator(mode="after")
    def _unique_items(self):
        ids = [item.itemId for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("itemId values must be unique")
        if not self.templateId and any(not item.templateId for item in self.items):
            raise ValueError("templateId is required on the batch or every item")
        return self
