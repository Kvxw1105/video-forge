from __future__ import annotations

from .internal import PaletteSpec, StrokeSpec, StyleContract


def make_style(renderer_id: str, theme_mode: str, ip_pack: str = "xuanqi") -> StyleContract:
    if theme_mode == "dark":
        palette = PaletteSpec(
            background="#090909",
            foreground="#F5F2E9",
            secondary="#BDB8AC",
            accent="#C63C32",
            muted="#5D5A54",
        )
    else:
        palette = PaletteSpec(
            background="#F5F1E8",
            foreground="#171717",
            secondary="#4D4A43",
            accent="#A52E28",
            muted="#B6B0A4",
        )
    opts = {}
    if renderer_id == "pixel_rules":
        opts = {"logical_width": 135, "logical_height": 240, "pixel_scale": 8, "frame_rate": 12}
    return StyleContract(
        style_id=f"{renderer_id}_{theme_mode}_{ip_pack}_v1",
        renderer_id=renderer_id,
        theme_mode=theme_mode,
        palette=palette,
        stroke=StrokeSpec(primary=15, secondary=9, detail=5),
        ip_pack=ip_pack,
        renderer_options=opts,
    )
