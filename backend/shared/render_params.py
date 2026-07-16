"""
Shared rendering parameters for FFmpeg renderer and JianYing draft adapter.
All coordinate/size/color conversions live here so both backends stay in sync
with the frontend CanvasPreview.
"""

from typing import Tuple


def subtitle_xy_exprs(position: str, w: int, h: int) -> Tuple[str, str]:
    """Return FFmpeg drawtext (x_expr, y_expr) for a 3x3 subtitle position preset.

    position format: "{vertical}_{horizontal}" e.g. "top_center", "middle_left".
    Coordinates are text-box anchored (centered horizontally, top or middle aligned).
    """
    if not position:
        position = "bottom_center"
    vert, _, horiz = position.partition("_")

    # Vertical: text box anchored
    if vert == "top":
        y = "h*0.08"
    elif vert == "middle":
        y = "(h-text_h)/2"
    else:  # bottom (default)
        y = "h-text_h-h*0.08"

    # Horizontal
    if horiz == "left":
        x = "w*0.05"
    elif horiz == "right":
        x = "w-text_w-w*0.05"
    else:  # center (default)
        x = "(w-text_w)/2"

    return x, y


def subtitle_to_jianying_transform(position: str) -> Tuple[float, float]:
    """Convert 3x3 subtitle position to JianYing transform_x/transform_y.

    JianYing: (0,0)=center, ±1=edge.
    """
    if not position:
        position = "bottom_center"
    vert, _, horiz = position.partition("_")
    transform_y_map = {"top": -0.78, "middle": 0.0, "bottom": 0.78}
    transform_x_map = {"left": -0.78, "center": 0.0, "right": 0.78}
    return transform_x_map.get(horiz, 0.0), transform_y_map.get(vert, 0.4)


def overlay_to_jianying_transform(x: float, y: float) -> Tuple[float, float]:
    """Convert normalized overlay position (0..1) to JianYing transform."""
    return (x - 0.5) * 2, (y - 0.5) * 2


def overlay_to_ffmpeg_exprs(x: float, y: float) -> Tuple[str, str]:
    """Convert normalized overlay position (0..1) to FFmpeg drawtext x/y expressions.

    Our overlay model uses center-anchor coordinates: (0.5, 0.5) is canvas center.
    FFmpeg drawtext x/y are top-left of the text box, so we subtract half text size.
    """
    return f"w*{x}-text_w/2", f"h*{y}-text_h/2"


def font_size_to_jianying(font_size: float) -> float:
    """Convert canvas pixel fontSize to JianYing TextStyle.size."""
    return max(2.0, font_size / 3.0)


def normalize_hex(color: str | None) -> str:
    """Normalize hex color to 6-digit lowercase string."""
    if not color:
        return "ffffff"
    c = color.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return (c[:6] or "ffffff").lower()


def ffmpeg_color_with_alpha(hex_color: str, opacity: float) -> str:
    """Return FFmpeg drawtext fontcolor string, with alpha when opacity < 1."""
    color = normalize_hex(hex_color)
    alpha = max(0.0, min(1.0, opacity))
    if alpha < 1.0:
        return f"0x{color}@{alpha:.2f}"
    return f"0x{color}"
