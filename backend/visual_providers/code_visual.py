from __future__ import annotations

import hashlib
import io
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .contracts import ProviderResult, SceneRequest


class CodeVisualProvider:
    """Structured visual renderer adapted to the current provider contract.

    The semantic templates mirror the donor code-visual pack: keyword,
    causal, process, comparison, ranking, topology, and mechanism. PNG is the
    canonical fast path; ``outputMode=video`` uses FFmpeg zoom/pan motion while
    preserving the incoming Scene window.
    """

    provider_id = "code_visual"
    provider_version = "1.0.0"
    trust = "TRUSTED_BUILTIN"
    template_ids = (
        "code_visual/keyword",
        "code_visual/causal",
        "code_visual/process",
        "code_visual/comparison",
        "code_visual/ranking",
        "code_visual/topology",
    )
    _COLORS = {
        "dark": ((9, 9, 9), (245, 242, 233), (198, 60, 50), (189, 184, 172)),
        "light": ((245, 241, 232), (23, 23, 23), (165, 46, 40), (77, 74, 67)),
    }

    def generate(self, request: SceneRequest) -> ProviderResult:
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            return ProviderResult(False, self.provider_id, self.provider_version, request.input_hash, error_code="provider_dependency_missing", error="Pillow is required by Code Visual")
        candidate_index = int(request.options.get("candidateIndex") or 0)
        seed = int(hashlib.sha256(f"{request.input_hash}:code:{candidate_index}".encode()).hexdigest()[:8], 16)
        theme = str(request.options.get("themeMode") or "dark")
        if theme not in self._COLORS:
            theme = "dark"
        template_id = self._template(request)
        width, height = max(160, request.width), max(160, request.height)
        background, foreground, accent, muted = self._COLORS[theme]
        image = Image.new("RGB", (width, height), background)
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        self._draw_template(draw, template_id, width, height, foreground, accent, muted, seed, font, request)
        # Candidate identity is part of the rendered pixels, not only
        # metadata, so candidateCount produces distinct deterministic media
        # while every candidate keeps the same Scene inputHash.
        marker_x = width - max(18, width // 18) - (seed % max(8, width // 30))
        marker_y = max(12, height // 24) + ((seed // 17) % max(8, height // 40))
        draw.ellipse((marker_x - 4, marker_y - 4, marker_x + 4, marker_y + 4), fill=accent)
        png_buffer = io.BytesIO()
        image.save(png_buffer, format="PNG", optimize=True)
        svg = self._svg(template_id, width, height, foreground, accent, theme, seed)
        metadata = {
            "templateId": template_id,
            "semanticType": template_id,
            "themeMode": theme,
            "seed": seed,
            "candidateIndex": candidate_index,
            "renderMode": "static",
            "timingSource": "scene_request_read_only",
        }
        output_mode = str(request.options.get("outputMode") or "static")
        if output_mode == "video":
            video = self._motion_video(png_buffer.getvalue(), width, height, request.duration, seed)
            if video is not None:
                metadata["renderMode"] = "motion_zoompan"
                return ProviderResult(True, self.provider_id, self.provider_version, request.input_hash, media_type="video/mp4", asset_kind="video", duration=request.duration, duration_policy="exact", filename=f"{request.scene_id}.mp4", data=video, sidecars={"svg": svg.encode("utf-8")}, metadata=metadata)
            metadata["renderMode"] = "static_fallback"
        return ProviderResult(True, self.provider_id, self.provider_version, request.input_hash, media_type="image/png", asset_kind="image", duration=None, duration_policy="exact", filename=f"{request.scene_id}.png", data=png_buffer.getvalue(), sidecars={"svg": svg.encode("utf-8")}, metadata=metadata)

    @staticmethod
    def _template(request: SceneRequest) -> str:
        raw = " ".join((request.text, str(request.options.get("finalPrompt") or ""), str(request.options.get("semanticIntent") or ""))).lower()
        if any(term in raw for term in ("节点", "拓扑", "node", "topology", "network", "knowledge")):
            return "topology"
        if any(term in raw for term in ("排名", "排行", "数字", "数据", "ranking", "score", "number", "data", "percent")):
            return "ranking"
        if any(term in raw for term in ("比较", "对比", "区别", "contrast", "compare", "versus")):
            return "comparison"
        if any(term in raw for term in ("流程", "步骤", "阶段", "process", "step", "progression", "pipeline")):
            return "process"
        if any(term in raw for term in ("因果", "原因", "结果", "导致", "cause", "effect", "consequence")):
            return "causal"
        if any(term in raw for term in ("机制", "结构", "原理", "system", "mechanism", "diagram")):
            return "mechanism"
        return "keyword"

    @staticmethod
    def _line(draw: Any, points: list[tuple[int, int]], fill: tuple[int, int, int], width: int = 5) -> None:
        draw.line(points, fill=fill, width=width, joint="curve")

    def _draw_template(self, draw: Any, template: str, width: int, height: int, fg: tuple[int, int, int], accent: tuple[int, int, int], muted: tuple[int, int, int], seed: int, font: Any, request: SceneRequest) -> None:
        cx, cy = width // 2, int(height * 0.44)
        stroke = max(2, round(width / 220))
        if template == "keyword":
            draw.ellipse((cx - width // 4, cy - width // 4, cx + width // 4, cy + width // 4), outline=accent, width=stroke * 2)
            draw.ellipse((cx - width // 12, cy - width // 12, cx + width // 12, cy + width // 12), fill=accent)
            self._line(draw, [(cx, cy - width // 3), (cx, cy + width // 3)], muted, stroke)
        elif template == "causal":
            left, right = width // 4, width * 3 // 4
            draw.rounded_rectangle((left - width // 8, cy - 45, left + width // 8, cy + 45), radius=18, outline=fg, width=stroke)
            draw.rounded_rectangle((right - width // 8, cy - 45, right + width // 8, cy + 45), radius=18, outline=accent, width=stroke)
            self._line(draw, [(left + width // 8, cy), (right - width // 8, cy)], accent, stroke * 2)
            draw.polygon([(right - width // 8, cy), (right - width // 8 - 20, cy - 15), (right - width // 8 - 20, cy + 15)], fill=accent)
        elif template == "process":
            points = [(width // 6 + i * width // 5, cy + (i % 2) * 40 - 20) for i in range(4)]
            for index, point in enumerate(points):
                draw.ellipse((point[0] - 24, point[1] - 24, point[0] + 24, point[1] + 24), fill=accent if index == 0 else fg)
                if index:
                    self._line(draw, [points[index - 1], point], muted, stroke)
        elif template == "comparison":
            base = int(height * 0.68)
            draw.rectangle((width // 4, base - 180, width * 2 // 5, base), fill=accent)
            draw.rectangle((width * 3 // 5, base - 110, width * 3 // 4, base), fill=fg)
            self._line(draw, [(width // 6, base), (width * 5 // 6, base)], muted, stroke)
        elif template == "ranking":
            base = int(height * 0.68)
            values = [0.45, 0.82, 0.62, 0.35]
            for index, value in enumerate(values):
                x = width // 7 + index * width // 5
                top = base - int(250 * value)
                draw.rectangle((x, top, x + width // 10, base), fill=accent if index == 1 else fg)
        elif template == "topology":
            nodes = [(cx, cy - 120), (cx - width // 4, cy + 80), (cx + width // 4, cy + 80), (cx, cy + 220)]
            for source, target in ((0, 1), (0, 2), (1, 3), (2, 3)):
                self._line(draw, [nodes[source], nodes[target]], muted, stroke)
            for index, (x, y) in enumerate(nodes):
                draw.ellipse((x - 28, y - 28, x + 28, y + 28), fill=accent if index == 0 else fg)
        else:
            draw.rounded_rectangle((width // 5, cy - 130, width * 4 // 5, cy + 130), radius=28, outline=fg, width=stroke)
            draw.ellipse((cx - 58, cy - 58, cx + 58, cy + 58), outline=accent, width=stroke * 2)
            self._line(draw, [(cx, cy + 58), (cx, cy + 160)], accent, stroke)
        label = template.replace("_", " ").upper()
        draw.text((width // 12, int(height * 0.83)), label, fill=fg, font=font)
        text = request.text[:42].replace("\n", " ")
        draw.text((width // 12, int(height * 0.88)), text, fill=muted, font=font)

    @staticmethod
    def _svg(template: str, width: int, height: int, fg: tuple[int, int, int], accent: tuple[int, int, int], theme: str, seed: int) -> str:
        root = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "width": str(width), "height": str(height), "viewBox": f"0 0 {width} {height}", "data-template": template, "data-theme": theme, "data-seed": str(seed)})
        ET.SubElement(root, "rect", {"width": str(width), "height": str(height), "fill": "#%02x%02x%02x" % (9, 9, 9) if theme == "dark" else "#f5f1e8"})
        ET.SubElement(root, "circle", {"cx": str(width // 2), "cy": str(height // 2), "r": str(max(20, width // 8)), "fill": "#%02x%02x%02x" % accent})
        return ET.tostring(root, encoding="unicode")

    @staticmethod
    def _motion_video(png: bytes, width: int, height: int, duration: float, seed: int) -> bytes | None:
        try:
            with tempfile.TemporaryDirectory(prefix="vf-code-motion-") as directory:
                root = Path(directory); image_path = root / "frame.png"; output = root / "scene.mp4"
                image_path.write_bytes(png)
                fps = 12; frames = max(1, round(duration * fps))
                zoom = "zoompan=z='min(zoom+0.0015,1.12)':d=%d:s=%dx%d:fps=%d" % (frames, width, height, fps)
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(image_path), "-vf", zoom, "-t", f"{duration:.3f}", "-an", "-pix_fmt", "yuv420p", str(output)], check=True, timeout=max(30, int(duration * 12) + 20))
                return output.read_bytes()
        except (OSError, subprocess.SubprocessError):
            return None
