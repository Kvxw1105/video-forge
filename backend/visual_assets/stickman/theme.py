from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StickmanStyle:
    stroke: str = "#FFFFFF"
    stroke_width: int = 12


def style_from_config(config) -> StickmanStyle:
    return StickmanStyle(stroke=config.theme.foreground, stroke_width=config.theme.lineWidth)
