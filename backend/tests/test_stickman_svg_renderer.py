import xml.etree.ElementTree as ET

from visual_assets.contracts import RenderConfig, RoutingOptions, VisualAssetSourceItem
from visual_assets.stickman.renderer import StickmanSvgProvider, validate_svg
from visual_assets.stickman.templates import TEMPLATES


def test_all_templates_render_valid_deterministic_svg():
    provider = StickmanSvgProvider()
    config = RenderConfig()
    for template_id in TEMPLATES:
        item = VisualAssetSourceItem(id=template_id, order=1, start=0, end=1, text=template_id, semantic={"templateId": template_id})
        route = provider.route(item, RoutingOptions())
        a = provider.render_svg(item, route, config).svg
        b = provider.render_svg(item, route, config).svg
        assert a == b
        assert validate_svg(a) == []
        root = ET.fromstring(a)
        assert root.attrib["viewBox"] == "0 0 1080 1920"
        assert "<text" not in a and "foreignObject" not in a
