from __future__ import annotations

from typing import Protocol

from .contracts import RenderConfig, RenderedSvg, RoutingOptions, VisualAssetRoute, VisualAssetSourceItem


class VisualAssetProvider(Protocol):
    provider_id: str
    provider_version: str

    def route(self, item: VisualAssetSourceItem, options: RoutingOptions) -> VisualAssetRoute:
        ...

    def render_svg(self, item: VisualAssetSourceItem, route: VisualAssetRoute, config: RenderConfig) -> RenderedSvg:
        ...
