from __future__ import annotations

from .stickman import StickmanSvgProvider
from .code_visual import CodeVisualSvgProvider

PROVIDERS = {
    "stickman_svg": StickmanSvgProvider(),
    "code_visual_svg": CodeVisualSvgProvider(),
}


def get_provider(provider_id: str):
    try:
        return PROVIDERS[provider_id]
    except KeyError as exc:
        raise KeyError(f"unknown provider: {provider_id}") from exc
