from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class SceneRequest:
    """Read-only canonical facts supplied to a Visual Provider."""

    project_id: str
    visual_plan_id: str
    scene_id: str
    block_id: str
    subtitle_ids: tuple[str, ...]
    text: str
    start: float
    end: float
    duration: float
    input_hash: str
    aspect_ratio: str
    width: int
    height: int
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResult:
    """Provider output; timing remains owned by the incoming SceneRequest."""

    success: bool
    provider_id: str
    provider_version: str
    input_hash: str
    media_type: str = "image/png"
    asset_kind: Literal["image", "video"] = "image"
    duration: float | None = None
    duration_policy: Literal["exact", "crop", "loop", "speed_adjust", "reject"] = "exact"
    filename: str = "scene.png"
    data: bytes = b""
    sidecars: dict[str, bytes] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    error_code: str = ""
    error: str = ""


class VisualProvider(Protocol):
    provider_id: str
    provider_version: str
    trust: Literal["LOCAL", "UNVERIFIED", "TRUSTED_BUILTIN"]
    template_ids: tuple[str, ...]

    def generate(self, request: SceneRequest) -> ProviderResult:
        """Generate a candidate without changing project or timing state."""
