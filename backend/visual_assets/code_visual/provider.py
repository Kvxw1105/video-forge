from __future__ import annotations

from visual_assets.contracts import RenderConfig, RenderedSvg, RoutingOptions, VisualAssetRoute, VisualAssetSourceItem

from .internal import SemanticSceneGraph, SubjectSpec
from .motion import resolve_motion
from .renderers import REGISTRY
from .themes import make_style

FAMILIES = ("control", "anxiety", "people_pleasing", "evidence", "awakening", "hidden_path", "trap_detection")


def _family(item: VisualAssetSourceItem) -> str:
    value = str(item.semantic.metadata.get("visualFamily") or item.semantic.visualIntent or item.semantic.topic or "").lower()
    mapping = {
        "relationship_control": "control", "red_string_pull": "control", "control": "control",
        "anxiety": "anxiety", "pressure": "anxiety", "people_pleasing": "people_pleasing",
        "evidence": "evidence", "awakening": "awakening", "escape": "awakening",
        "hidden_path": "hidden_path", "trap": "trap_detection",
    }
    if value in FAMILIES:
        return value
    return mapping.get(value, "anxiety")


def _recommended_renderer(family: str) -> tuple[str, str]:
    if family in {"control", "people_pleasing", "awakening"}:
        return "white_sketch", "dark"
    if family == "anxiety":
        return "silhouette", "dark"
    if family in {"evidence"}:
        return "mechanism_diagram", "light"
    return "pixel_rules", "dark"


class CodeVisualSvgProvider:
    provider_id = "code_visual_svg"
    provider_version = "0.5.0"

    def route(self, item: VisualAssetSourceItem, options: RoutingOptions) -> VisualAssetRoute:
        meta = item.semantic.metadata
        family = _family(item)
        renderer, theme = _recommended_renderer(family)
        renderer = str(meta.get("rendererId") or item.semantic.templateId or renderer)
        if renderer not in REGISTRY:
            renderer = _recommended_renderer(family)[0]
        theme = str(meta.get("themeMode") or theme)
        if theme not in {"dark", "light"}:
            theme = "dark"
        ip_pack = str(meta.get("ipPack") or "neutral")
        if ip_pack not in {"neutral", "xuanqi", "huicewolf", "ayin"}:
            ip_pack = "neutral"
        return VisualAssetRoute(
            templateId=f"{renderer}:{family}",
            templateVersion=self.provider_version,
            confidence=0.9 if meta.get("rendererId") else 0.76,
            parameters={"rendererId": renderer, "themeMode": theme, "ipPack": ip_pack, "visualFamily": family},
            reason="explicit_renderer" if meta.get("rendererId") else "deterministic_recommendation",
        )

    def render_svg(self, item: VisualAssetSourceItem, route: VisualAssetRoute, config: RenderConfig) -> RenderedSvg:
        params = route.parameters
        renderer_id = str(config.providerOptions.get("rendererId") or params["rendererId"])
        if renderer_id == "auto":
            renderer_id = str(params["rendererId"])
        theme = str(config.providerOptions.get("themeMode") or params["themeMode"])
        ip_pack = str(config.providerOptions.get("ipPack") or params["ipPack"])
        family = str(params["visualFamily"])
        if renderer_id not in REGISTRY:
            raise KeyError(renderer_id)
        subject = SubjectSpec(type="pair" if item.semantic.actors >= 2 else "person", count=item.semantic.actors)
        scene = SemanticSceneGraph(
            scene_id=item.id, order=item.order, block_id=item.blockId, subtitle_ids=item.subtitleIds,
            start=item.start, end=item.end, text=item.text, subject=subject, topic=item.semantic.topic,
            emotion=item.semantic.emotion, visual_family=family, composition_family=family,
            ip_pack=ip_pack, preferred_renderer=renderer_id, motion_profile=family,
            metadata=item.semantic.metadata,
        )
        style = make_style(renderer_id, theme, ip_pack).model_copy(update={"seed": config.seed})
        svg, template, layers = REGISTRY[renderer_id].render_svg(scene, style)
        motion = resolve_motion(scene, style).model_dump(mode="json")
        return RenderedSvg(svg=svg, templateId=template, templateVersion=self.provider_version, parameters={**params, "rendererId": renderer_id, "themeMode": theme, "ipPack": ip_pack}, composition={"anchor": "center", "safeArea": "bottom_24"}, motionHint={"schemaVersion": 1, "motionPlan": motion, "layerIds": layers})
