from __future__ import annotations

import xml.etree.ElementTree as ET

from visual_assets.contracts import RenderConfig, RenderedSvg, RoutingOptions, VisualAssetRoute, VisualAssetSourceItem
from .routing import route_item
from .templates import TEMPLATES
from .theme import style_from_config


class StickmanSvgProvider:
    provider_id = "stickman_svg"
    provider_version = "0.1.0"

    def route(self, item: VisualAssetSourceItem, options: RoutingOptions) -> VisualAssetRoute:
        return route_item(item, options)

    def render_svg(self, item: VisualAssetSourceItem, route: VisualAssetRoute, config: RenderConfig) -> RenderedSvg:
        template = TEMPLATES[route.templateId]
        params = template.validate_parameters(route.parameters)
        svg = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "width": str(config.canvas.width), "height": str(config.canvas.height), "viewBox": f"0 0 {config.canvas.width} {config.canvas.height}"})
        group = ET.SubElement(svg, "g", {"fill": "none"})
        template.draw(group, style_from_config(config), params)
        return RenderedSvg(svg=ET.tostring(svg, encoding="unicode", short_empty_elements=True), templateId=template.template_id, templateVersion=template.template_version, parameters=params, composition=template.default_composition, motionHint=template.default_motion_hint)


ALLOWED_TAGS = {"svg", "g", "circle", "ellipse", "line", "polyline", "polygon", "path", "rect", "defs", "clipPath"}
BANNED_TAGS = {"script", "foreignObject", "text", "image", "animate", "filter", "linearGradient", "radialGradient"}


def validate_svg(svg_text: str, width: int = 1080, height: int = 1920) -> list[str]:
    if not svg_text or not svg_text.strip():
        return ["svg file is empty"]
    errors = []
    if "NaN" in svg_text or "Infinity" in svg_text:
        errors.append("svg contains non-finite value")
    if "data:" in svg_text:
        errors.append("svg contains external reference")
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as exc:
        return [f"xml parse failed: {exc}"]
    local = lambda tag: tag.rsplit("}", 1)[-1]
    if local(root.tag) != "svg":
        errors.append("root is not svg")
    if root.attrib.get("viewBox") != f"0 0 {width} {height}":
        errors.append("viewBox mismatch")
    if root.attrib.get("width") != str(width) or root.attrib.get("height") != str(height):
        errors.append("dimensions mismatch")
    visible = 0
    for elem in root.iter():
        name = local(elem.tag)
        if name in BANNED_TAGS:
            errors.append(f"banned tag: {name}")
        if name not in ALLOWED_TAGS:
            errors.append(f"unsupported tag: {name}")
        for value in elem.attrib.values():
            if "NaN" in value or "Infinity" in value:
                errors.append("attribute contains non-finite value")
            if (value.startswith("http://") or value.startswith("https://") or value.startswith("data:")) and value != "http://www.w3.org/2000/svg":
                errors.append("attribute contains external reference")
        if name in {"circle", "ellipse", "line", "polyline", "polygon", "path", "rect"}:
            visible += 1
        if name == "rect" and elem.attrib.get("x") in {"0", "0.0"} and elem.attrib.get("y") in {"0", "0.0"} and elem.attrib.get("width") == str(width) and elem.attrib.get("height") == str(height):
            fill = elem.attrib.get("fill", "none")
            if fill not in {"none", "transparent"} and elem.attrib.get("opacity") not in {"0", "0.0"}:
                errors.append("full canvas opaque background")
    if visible == 0:
        errors.append("no visible elements")
    return sorted(set(errors))
