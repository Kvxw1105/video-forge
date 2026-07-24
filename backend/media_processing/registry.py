from __future__ import annotations

from .mediakit_provider import MediaKitProvider
from .native_provider import VideoForgeNativeMediaProvider


def get_provider(provider_id: str | None = None):
    selected = provider_id or "videoforge_native"
    if selected == "videoforge_native":
        return VideoForgeNativeMediaProvider()
    if selected == "mediakit":
        return MediaKitProvider()
    raise ValueError(f"unknown media provider: {selected}")


def discover_providers() -> list[dict]:
    return [VideoForgeNativeMediaProvider().discover(), MediaKitProvider().discover()]
