from __future__ import annotations

import os
import struct
import subprocess
import zlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class RasterizeResult:
    succeeded: bool
    png_path: Path | None = None
    error_code: str | None = None
    message: str = ""


class SvgRasterizer(Protocol):
    rasterizer_id: str
    rasterizer_version: str

    def is_available(self) -> bool: ...
    def rasterize(self, svg_path: Path, png_path: Path, width: int, height: int) -> RasterizeResult: ...


class FfmpegSvgRasterizer:
    rasterizer_id = "ffmpeg_svg"
    rasterizer_version = "system"

    def is_available(self) -> bool:
        try:
            probe = subprocess.run(["ffmpeg", "-hide_banner", "-version"], capture_output=True, text=True, timeout=5)
            return probe.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def rasterize(self, svg_path: Path, png_path: Path, width: int, height: int) -> RasterizeResult:
        if not self.is_available():
            return RasterizeResult(False, None, "png_converter_unavailable", "ffmpeg is not available")
        tmp = png_path.with_name("." + png_path.stem + ".tmp.png")
        tmp.unlink(missing_ok=True)
        cmd = ["ffmpeg", "-hide_banner", "-y", "-i", str(svg_path), "-vf", f"scale={width}:{height}:flags=lanczos,format=rgba", "-frames:v", "1", "-f", "image2", str(tmp)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
            tmp.unlink(missing_ok=True)
            return RasterizeResult(False, None, "png_render_failed", (proc.stderr or proc.stdout)[-500:])
        os.replace(tmp, png_path)
        return RasterizeResult(True, png_path)


class PillowSvgRasterizer:
    """Offline rasterizer for the restricted SVG primitives emitted by this provider."""

    rasterizer_id = "pillow_restricted_svg"
    rasterizer_version = "1"

    def is_available(self) -> bool:
        try:
            from PIL import Image, ImageDraw  # noqa: F401
            return True
        except ImportError:
            return False

    def rasterize(self, svg_path: Path, png_path: Path, width: int, height: int) -> RasterizeResult:
        if not self.is_available():
            return RasterizeResult(False, None, "png_converter_unavailable", "Pillow is not available")
        tmp = png_path.with_name("." + png_path.stem + ".tmp.png")
        tmp.unlink(missing_ok=True)
        try:
            from PIL import Image, ImageDraw

            root = ET.parse(svg_path).getroot()
            source_width = float(root.attrib.get("width", width))
            source_height = float(root.attrib.get("height", height))
            sx, sy = width / source_width, height / source_height
            image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)

            def local(tag: str) -> str:
                return tag.rsplit("}", 1)[-1]

            def color(element):
                raw = element.attrib.get("stroke", "#FFFFFF")
                alpha = round(float(element.attrib.get("opacity", "1")) * 255)
                if raw.startswith("#") and len(raw) == 7:
                    return tuple(int(raw[index:index + 2], 16) for index in (1, 3, 5)) + (alpha,)
                return (255, 255, 255, alpha)

            def number(value, default=0.0):
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return default

            def points(value):
                values = [number(item) for item in value.replace(",", " ").split()]
                return [(values[index] * sx, values[index + 1] * sy) for index in range(0, len(values) - 1, 2)]

            for element in root.iter():
                tag = local(element.tag)
                stroke = color(element)
                line_width = max(1, round(number(element.attrib.get("stroke-width"), 1) * min(sx, sy)))
                if tag == "line":
                    draw.line((number(element.attrib.get("x1")) * sx, number(element.attrib.get("y1")) * sy, number(element.attrib.get("x2")) * sx, number(element.attrib.get("y2")) * sy), fill=stroke, width=line_width)
                elif tag == "circle":
                    cx, cy, radius = number(element.attrib.get("cx")) * sx, number(element.attrib.get("cy")) * sy, number(element.attrib.get("r")) * min(sx, sy)
                    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=stroke, width=line_width)
                elif tag == "ellipse":
                    cx, cy = number(element.attrib.get("cx")) * sx, number(element.attrib.get("cy")) * sy
                    rx, ry = number(element.attrib.get("rx")) * sx, number(element.attrib.get("ry")) * sy
                    draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), outline=stroke, width=line_width)
                elif tag == "rect":
                    x, y = number(element.attrib.get("x")) * sx, number(element.attrib.get("y")) * sy
                    w, h = number(element.attrib.get("width")) * sx, number(element.attrib.get("height")) * sy
                    draw.rectangle((x, y, x + w, y + h), outline=stroke, width=line_width)
                elif tag in {"polyline", "polygon"}:
                    pts = points(element.attrib.get("points", ""))
                    if len(pts) >= 2:
                        draw.line(pts + ([pts[0]] if tag == "polygon" else []), fill=stroke, width=line_width, joint="curve")
            image.save(tmp, "PNG")
            if tmp.stat().st_size == 0:
                raise RuntimeError("Pillow emitted an empty PNG")
            os.replace(tmp, png_path)
            return RasterizeResult(True, png_path)
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            return RasterizeResult(False, None, "png_render_failed", str(exc))


def parse_png(path: Path) -> dict:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("invalid PNG signature")
    pos = 8
    width = height = color_type = None
    idat = b""
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos+4])[0]; pos += 4
        chunk = data[pos:pos+4]; pos += 4
        payload = data[pos:pos+length]; pos += length + 4
        if chunk == b"IHDR":
            width, height, _bit_depth, color_type, _comp, _filter, _interlace = struct.unpack(">IIBBBBB", payload)
        elif chunk == b"IDAT":
            idat += payload
        elif chunk == b"IEND":
            break
    return {"width": width, "height": height, "color_type": color_type, "idat": idat}


def validate_png_alpha(path: Path, width: int, height: int) -> list[str]:
    errors = []
    try:
        info = parse_png(path)
    except Exception as exc:
        return [str(exc)]
    if info["width"] != width or info["height"] != height:
        errors.append("dimensions mismatch")
    if info["color_type"] not in {4, 6}:
        errors.append("png has no alpha channel")
    if info["idat"]:
        try:
            raw = zlib.decompress(info["idat"])
            if raw and all(byte == 0 for byte in raw):
                errors.append("png appears fully transparent or empty")
        except zlib.error:
            pass
    return errors
