from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .cache import atomic_write_text
from .contracts import VisualAssetManifest

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def build_contact_sheet_svg(manifest: VisualAssetManifest, output_path: Path) -> Path:
    cols = 3
    card_w, card_h = 360, 360
    rows = max(1, (len(manifest.items) + cols - 1) // cols)
    root = ET.Element(f"{{{SVG_NS}}}svg", {"width": str(cols * card_w), "height": str(rows * card_h), "viewBox": f"0 0 {cols * card_w} {rows * card_h}"})
    for index, item in enumerate(sorted(manifest.items, key=lambda x: x.order)):
        x = (index % cols) * card_w
        y = (index // cols) * card_h
        group = ET.SubElement(root, "g")
        ET.SubElement(group, "rect", {"x": str(x + 8), "y": str(y + 8), "width": str(card_w - 16), "height": str(card_h - 16), "fill": "#111111", "stroke": "#666666"})
        ET.SubElement(group, "text", {"x": str(x + 22), "y": str(y + 38), "fill": "#ffffff", "font-size": "16"}).text = f"{item.order:04d} {item.segmentId[:28]}"
        ET.SubElement(group, "text", {"x": str(x + 22), "y": str(y + 62), "fill": "#ffffff", "font-size": "14"}).text = f"{item.templateId} / {item.status}"
        ET.SubElement(group, "text", {"x": str(x + 22), "y": str(y + 86), "fill": "#cccccc", "font-size": "12"}).text = item.text[:42]
        if item.svgPath:
            try:
                svg = ET.parse(output_path.parent / item.svgPath).getroot()
                thumb = ET.SubElement(group, "g", {"transform": f"translate({x + 50},{y + 105}) scale(0.22)"})
                for child in list(svg):
                    thumb.append(child)
            except Exception:
                ET.SubElement(group, "text", {"x": str(x + 22), "y": str(y + 150), "fill": "#ff9999", "font-size": "13"}).text = "thumbnail unavailable"
    atomic_write_text(output_path, ET.tostring(root, encoding="unicode", short_empty_elements=True))
    return output_path
