from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Optional, Literal, Union
from datetime import datetime


STRUCTURED_BLOCK_TYPES = Literal[
    "HOOK", "CTA_TAG", "PROBLEM", "STORY", "MECHANISM", "JUDGMENT",
    "METHOD", "SHORT_OUTRO", "BRIDGE_IN", "BRIDGE_OUT", "COMMENT_CTA",
]


class StructuredBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    type: STRUCTURED_BLOCK_TYPES
    text: str = ""
    enabled: bool = True
    revision: int = Field(default=1, ge=1)
    metadata: dict = Field(default_factory=dict)


class StructuredVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = ""
    blockIds: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    @field_validator("blockIds")
    @classmethod
    def _unique_block_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("variant blockIds must be unique")
        if any(not isinstance(item, str) or not item for item in value):
            raise ValueError("variant blockIds must contain non-empty strings")
        return value


class StructuredAudioSlice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voiceoverId: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    sourceStart: float = Field(ge=0)
    sourceEnd: float = Field(gt=0)

    @model_validator(mode="after")
    def _validate_range(self):
        if self.sourceEnd <= self.sourceStart:
            raise ValueError("audioSlice sourceEnd must be greater than sourceStart")
        return self


class BlockAssetBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blockId: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    audioSlice: StructuredAudioSlice | None = None
    visualAssetIds: list[str] = Field(default_factory=list)
    subtitleIds: list[str] = Field(default_factory=list)
    duration: float | None = Field(default=None, gt=0)
    metadata: dict = Field(default_factory=dict)

    @field_validator("visualAssetIds", "subtitleIds")
    @classmethod
    def _unique_refs(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("binding references must be unique")
        if any(not isinstance(item, str) or not item for item in value):
            raise ValueError("binding references must contain non-empty strings")
        return value

    @model_validator(mode="after")
    def _require_duration(self):
        if self.audioSlice is None and self.duration is None:
            raise ValueError("binding requires audioSlice or positive duration")
        if self.audioSlice is not None and self.duration is not None:
            actual = self.audioSlice.sourceEnd - self.audioSlice.sourceStart
            if abs(actual - self.duration) > 0.05:
                # The compiler emits the user-facing warning; the model only
                # rejects impossible/non-positive values.
                object.__setattr__(self, "duration", self.duration)
        return self


class StructuredEpisode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episodeId: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = ""
    topic: str = ""
    symbol: str = ""
    blocks: list[StructuredBlock] = Field(default_factory=list)
    variants: list[StructuredVariant] = Field(default_factory=list)
    bindings: list[BlockAssetBinding] = Field(default_factory=list)
    activeVariantId: str | None = None
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_references(self):
        block_ids = [block.id for block in self.blocks]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("structured episode block ids must be unique")
        variant_ids = [variant.id for variant in self.variants]
        if len(variant_ids) != len(set(variant_ids)):
            raise ValueError("structured episode variant ids must be unique")
        known_blocks = set(block_ids)
        for variant in self.variants:
            missing = [item for item in variant.blockIds if item not in known_blocks]
            if missing:
                raise ValueError(f"variant {variant.id} references missing blocks: {', '.join(missing)}")
        if variant_ids and self.activeVariantId is None:
            raise ValueError("activeVariantId is required when variants are present")
        if self.activeVariantId is not None and self.activeVariantId not in set(variant_ids):
            raise ValueError("activeVariantId must reference an existing variant")
        binding_ids = [binding.blockId for binding in self.bindings]
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("structured episode binding block ids must be unique")
        if any(binding_id not in set(block_ids) for binding_id in binding_ids):
            raise ValueError("binding blockId must reference an existing block")
        return self


class StructuredContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal[1] = 1
    episode: StructuredEpisode

class Canvas(BaseModel):
    ratio: Literal["9:16", "16:9", "1:1", "4:5", "4:3"] = "9:16"
    width: int = 1080
    height: int = 1920
    fps: int = 30
    background: dict = Field(default_factory=lambda: {"type": "color", "value": "#000000"})

class Asset(BaseModel):
    id: str
    type: Literal["image", "audio", "video", "other"]
    name: str
    path: str
    metadata: dict = Field(default_factory=dict)

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, v: str) -> str:
        # "other" 不是合法类型——归为 video，防止 Pydantic 崩溃
        if v == "other":
            return "video"
        return v

class Segment(BaseModel):
    id: str
    assetPath: str
    type: Literal["image", "video", "black"]
    start: float = 0.0
    end: float = 0.0
    transform: dict = Field(default_factory=lambda: {
        "x": 0.5, "y": 0.5, "scale": 0.85, "rotation": 0, "fit": "contain"
    })
    animation: Optional[dict] = None

class TimelineBlock(BaseModel):
    type: Literal["black", "assets"] = "assets"
    duration: Union[float, Literal["rest"]] = "rest"
    source: Literal["all", "images", "videos"] = "all"
    mode: Literal["random", "ordered"] = "random"
    perAssetDuration: float = 1.0
    bgColor: str = "#000000"


class Timeline(BaseModel):
    voiceoverStartAt: float = 0.0
    blocks: list[TimelineBlock] = Field(default_factory=list)


class AudioConfig(BaseModel):
    id: str = ""
    api: str = "manbo_vip"  # edge | manbo_vip | manbo_free | custom
    voice: str = "manbo"
    speed: float = 0.0
    pitch: float = 0.0
    volume: float = 1.0
    file: str = ""
    duration: float = 0.0
    text: str = ""
    engine: str = "edge"
    isActive: bool = True
    createdAt: str = Field(default_factory=lambda: datetime.now().isoformat())

class BGMTrack(BaseModel):
    file: str = ""
    volume: float = 0.3
    trimStart: float = 0.0
    trimEnd: float = 0.0  # 0 = 不裁剪，用完整时长
    startAt: float = 0.0  # 在视频时间线第几秒开始播放
    fadeIn: float = 0.0
    fadeOut: float = 0.0

class SFXTrack(BaseModel):
    file: str = ""
    startAt: float = 0.0
    volume: float = 0.8
    trimStart: float = 0.0
    trimEnd: float = 0.0

class BGMConfig(BaseModel):
    tracks: list[BGMTrack] = Field(default_factory=list)
    # 兼容旧数据：如果只有 file 字段（旧格式），自动迁移
    file: str = ""
    volume: float = 0.3
    loop: bool = True
    fadeIn: float = 0.0
    fadeOut: float = 2.0

class Audio(BaseModel):
    voiceover: AudioConfig = Field(default_factory=AudioConfig)
    voiceovers: list[AudioConfig] = Field(default_factory=list)
    bgm: BGMConfig = Field(default_factory=BGMConfig)
    sfx: list[SFXTrack] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _migrate_single_voiceover(cls, data):
        """兼容旧数据：如果只有 audio.voiceover 没有 voiceovers，自动迁移。"""
        if not isinstance(data, dict):
            return data
        vlist = data.get("voiceovers")
        old = data.get("voiceover")
        legacy_file = old.get("file") if isinstance(old, dict) else ""
        legacy_duration = float(old.get("duration", 0) or 0) if isinstance(old, dict) else 0.0
        legacy_text = old.get("text", "") if isinstance(old, dict) else ""
        is_placeholder = legacy_file == "voiceover.mp3" and legacy_duration <= 0 and not legacy_text
        if (not vlist or len(vlist) == 0) and old and isinstance(old, dict) and old.get("file") and not is_placeholder:
            migrated = {**old, "id": old.get("id") or "vo_1", "isActive": True}
            data["voiceovers"] = [migrated]
        return data

class Subtitle(BaseModel):
    id: str
    text: str
    start: float
    end: float
    style: dict = Field(default_factory=lambda: {
        "fontSize": 48, "color": "#ffffff",
        "strokeColor": "#000000", "strokeWidth": 2, "position": "bottom_center"
    })

class DirectoryProgress(BaseModel):
    enabled: bool = False
    mode: Literal["marquee_text", "marker_line", "chapter_highlight"] = "marquee_text"
    text: str = "起势｜转折｜高潮｜余韵"
    fontSize: int = 22
    color: str = "#F4EBDD"
    opacity: float = 0.72
    y: float = 0.94
    startX: float = -0.35
    endX: float = 1.05


class Overlay(BaseModel):
    title: dict = Field(default_factory=lambda: {
        "text": "", "position": "top_center", "fontSize": 48,
        "color": "#ffffff", "opacity": 1.0, "enabled": False,
        "x": 0.5, "y": 0.08
    })
    watermark: dict = Field(default_factory=lambda: {
        "text": "", "position": "bottom_right", "fontSize": 24,
        "color": "#ffffff", "opacity": 0.35, "enabled": False,
        "x": 0.85, "y": 0.92
    })
    adjustments: dict = Field(default_factory=lambda: {
        "brightness": 0.0, "contrast": 1.0  # brightness: -1~1, contrast: 0~2
    })
    directoryProgress: DirectoryProgress = Field(default_factory=DirectoryProgress)
    subtitle_enabled: bool = True

class ExportSettings(BaseModel):
    targets: list[str] = ["jianying_draft"]
    outputDir: str = ""

class Project(BaseModel):
    id: str = ""
    name: str = "未命名项目"
    version: str = "0.1"
    canvas: Canvas = Field(default_factory=Canvas)
    templateId: str = "single_image_voiceover"
    visualMode: Literal["single", "carousel"] = "single"
    assets: list[Asset] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)
    audio: Audio = Field(default_factory=Audio)
    subtitles: list[Subtitle] = Field(default_factory=list)
    overlays: Overlay = Field(default_factory=Overlay)
    exportSettings: ExportSettings = Field(default_factory=ExportSettings)
    script: str = ""  # User-input script text, persisted across sessions
    # Timeline / composition settings (persisted across sessions)
    perImageDuration: float = 1.0
    shuffleMode: bool = True
    timeline: Timeline = Field(default_factory=Timeline)
    structuredContent: StructuredContent | None = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    @model_validator(mode="before")
    @classmethod
    def _infer_legacy_visual_mode(cls, data):
        if not isinstance(data, dict) or data.get("visualMode") in {"single", "carousel"}:
            return data

        migrated = dict(data)
        template_id = str(migrated.get("templateId") or "")
        if "carousel" in template_id:
            migrated["visualMode"] = "carousel"
            return migrated

        visual_paths = {
            str(segment.get("assetPath") or "")
            for segment in migrated.get("segments") or []
            if isinstance(segment, dict)
            and segment.get("type") != "black"
            and segment.get("assetPath")
        }
        migrated["visualMode"] = "carousel" if len(visual_paths) > 1 else "single"
        return migrated
