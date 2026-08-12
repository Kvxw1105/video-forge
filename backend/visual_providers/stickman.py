from __future__ import annotations

import hashlib
import io
import math
import xml.etree.ElementTree as ET
from typing import Any

from .contracts import ProviderResult, SceneRequest


class StickmanProvider:
    """Deterministic local PNG provider with an SVG source sidecar."""

    provider_id = "stickman"
    provider_version = "1.0.0"
    trust = "TRUSTED_BUILTIN"
    template_ids = (
        "stickman/inner_conflict",
        "stickman/escape_enclosure",
        "stickman/relationship_tug",
        "stickman/burden_boulder",
        "stickman/generic_two_person_relation",
    )

    _PALETTE = ((47, 43, 38, 255), (99, 77, 57, 255), (67, 81, 78, 255))

    def generate(self, request: SceneRequest) -> ProviderResult:
        try:
            from PIL import Image, ImageDraw
        except ImportError as exc:
            return ProviderResult(
                success=False,
                provider_id=self.provider_id,
                provider_version=self.provider_version,
                input_hash=request.input_hash,
                error_code="provider_dependency_missing",
                error="Pillow is required by the local Stickman Provider",
            )

        candidate_index = int(request.options.get("candidateIndex") or 0)
        seed = int(hashlib.sha256(f"{request.input_hash}:{request.scene_id}:{candidate_index}".encode()).hexdigest()[:8], 16)
        template_id = self._template(request.text, seed)
        width, height = max(64, request.width), max(64, request.height)
        stroke = self._PALETTE[seed % len(self._PALETTE)]
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        scale = min(width / 1080.0, height / 1920.0)
        line_width = max(3, round(12 * scale))
        cx, cy = width * 0.5, height * 0.48

        self._draw_scene(draw, template_id, cx, cy, scale, stroke, line_width, seed)
        # Keep candidate identity visible in the bytes even when two seeds
        # happen to select the same semantic template and geometry.
        marker = max(2, round(8 * scale))
        draw.rectangle((marker, marker, marker + candidate_index * 3 + 2, marker + 2), fill=stroke)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        png = buffer.getvalue()
        svg = self._svg(template_id, width, height, stroke, seed)
        return ProviderResult(
            success=True,
            provider_id=self.provider_id,
            provider_version=self.provider_version,
            input_hash=request.input_hash,
            filename=f"{request.scene_id}.png",
            data=png,
            sidecars={"svg": svg.encode("utf-8")},
            metadata={
                "templateId": template_id,
                "seed": seed,
                "candidateIndex": candidate_index,
                "renderedAt": "deterministic",
                "timingSource": "scene_request_read_only",
            },
        )

    @staticmethod
    def _template(text: str, seed: int) -> str:
        value = text.lower()
        if any(word in value for word in ("冲突", "矛盾", "拉扯", "压力", "选择")):
            return "inner_conflict"
        if any(word in value for word in ("逃", "离开", "突破", "摆脱", "自由")):
            return "escape_enclosure"
        if any(word in value for word in ("关系", "沟通", "连接", "合作", "对话")):
            return "relationship_tug"
        return ("burden_boulder", "generic_single_person", "generic_two_person_relation")[seed % 3]

    @staticmethod
    def _line(draw: Any, points: list[tuple[float, float]], fill: tuple[int, int, int, int], width: int) -> None:
        draw.line(points, fill=fill, width=width, joint="curve")

    def _person(self, draw: Any, x: float, y: float, scale: float, fill: tuple[int, int, int, int], width: int, *, lean: float = 0.0, reach: float = 0.0) -> None:
        head = 42 * scale
        torso = 155 * scale
        draw.ellipse((x - head, y - head, x + head, y + head), outline=fill, width=width)
        shoulder = (x, y + head + 28 * scale)
        hip = (x + lean * scale, y + head + torso * scale)
        self._line(draw, [shoulder, hip], fill, width)
        self._line(draw, [shoulder, (x - 75 * scale, shoulder[1] + 70 * scale), (x - 120 * scale, shoulder[1] + (110 + reach) * scale)], fill, width)
        self._line(draw, [shoulder, (x + 75 * scale, shoulder[1] + 70 * scale), (x + 120 * scale, shoulder[1] + (110 - reach) * scale)], fill, width)
        self._line(draw, [hip, (hip[0] - 65 * scale, hip[1] + 80 * scale), (hip[0] - 95 * scale, hip[1] + 155 * scale)], fill, width)
        self._line(draw, [hip, (hip[0] + 65 * scale, hip[1] + 80 * scale), (hip[0] + 95 * scale, hip[1] + 155 * scale)], fill, width)

    def _draw_scene(self, draw: Any, template: str, cx: float, cy: float, scale: float, fill: tuple[int, int, int, int], width: int, seed: int) -> None:
        if template == "inner_conflict":
            self._person(draw, cx - 180 * scale, cy, scale, fill, width, lean=-22, reach=18)
            self._person(draw, cx + 180 * scale, cy, scale, fill, width, lean=22, reach=-18)
            self._line(draw, [(cx, cy + 40 * scale), (cx - 28 * scale, cy + 95 * scale), (cx + 22 * scale, cy + 145 * scale), (cx - 10 * scale, cy + 205 * scale)], fill, width)
        elif template == "escape_enclosure":
            draw.rectangle((cx - 250 * scale, cy - 250 * scale, cx + 60 * scale, cy + 400 * scale), outline=fill, width=width)
            self._person(draw, cx + 210 * scale, cy, scale, fill, width, lean=-20, reach=45)
            self._line(draw, [(cx + 60 * scale, cy + 100 * scale), (cx + 145 * scale, cy + 25 * scale), (cx + 230 * scale, cy + 100 * scale)], fill, width)
        elif template == "relationship_tug":
            self._person(draw, cx - 190 * scale, cy, scale, fill, width, reach=25)
            self._person(draw, cx + 190 * scale, cy, scale, fill, width, reach=-25)
            self._line(draw, [(cx - 110 * scale, cy + 120 * scale), (cx, cy + 82 * scale), (cx + 110 * scale, cy + 120 * scale)], fill, width)
        elif template == "burden_boulder":
            self._person(draw, cx, cy + 40 * scale, scale, fill, width, lean=18)
            draw.ellipse((cx - 120 * scale, cy - 290 * scale, cx + 120 * scale, cy - 50 * scale), outline=fill, width=width)
            draw.ellipse((cx - 150 * scale, cy + 310 * scale, cx + 150 * scale, cy + 365 * scale), outline=fill, width=max(2, width // 2))
        elif template == "generic_two_person_relation":
            self._person(draw, cx - 175 * scale, cy, scale, fill, width)
            self._person(draw, cx + 175 * scale, cy, scale, fill, width)
            draw.ellipse((cx - 32 * scale, cy - 200 * scale, cx + 32 * scale, cy - 136 * scale), outline=fill, width=width)
        else:
            self._person(draw, cx, cy, scale, fill, width, lean=(seed % 31) - 15)
            draw.ellipse((cx - 250 * scale, cy + 300 * scale, cx + 250 * scale, cy + 365 * scale), outline=fill, width=max(2, width // 2))

    @staticmethod
    def _svg(template: str, width: int, height: int, fill: tuple[int, int, int, int], seed: int) -> str:
        color = "#%02x%02x%02x" % fill[:3]
        root = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "width": str(width), "height": str(height), "viewBox": f"0 0 {width} {height}", "data-template": template, "data-seed": str(seed)})
        group = ET.SubElement(root, "g", {"fill": "none", "stroke": color, "stroke-width": "12", "stroke-linecap": "round", "stroke-linejoin": "round"})
        ET.SubElement(group, "circle", {"cx": str(width // 2), "cy": str(height // 2 - 240), "r": "42"})
        ET.SubElement(group, "line", {"x1": str(width // 2), "y1": str(height // 2 - 195), "x2": str(width // 2), "y2": str(height // 2 + 20)})
        ET.SubElement(group, "line", {"x1": str(width // 2), "y1": str(height // 2 + 20), "x2": str(width // 2 - 90), "y2": str(height // 2 + 175)})
        ET.SubElement(group, "line", {"x1": str(width // 2), "y1": str(height // 2 + 20), "x2": str(width // 2 + 90), "y2": str(height // 2 + 175)})
        return ET.tostring(root, encoding="unicode", short_empty_elements=True)
