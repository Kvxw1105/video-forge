from __future__ import annotations

from .contracts import VisualProvider

_PROVIDERS: dict[str, VisualProvider] = {}


def register_provider(provider: VisualProvider) -> VisualProvider:
    _PROVIDERS[provider.provider_id] = provider
    return provider


def get_provider(provider_id: str) -> VisualProvider:
    # Import lazily so the registry remains cheap for normal API startup.
    if not _PROVIDERS:
        from .stickman import StickmanProvider

        register_provider(StickmanProvider())
    try:
        return _PROVIDERS[provider_id]
    except KeyError as exc:
        raise KeyError(f"visual_provider_not_found:{provider_id}") from exc


def list_providers() -> list[dict[str, str]]:
    if not _PROVIDERS:
        get_provider("stickman")
    return [
        {"providerId": provider.provider_id, "version": provider.provider_version}
        for provider in sorted(_PROVIDERS.values(), key=lambda item: item.provider_id)
    ]
