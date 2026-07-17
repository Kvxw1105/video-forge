"""Lower provider-neutral visual keyframes to JianYing segment keyframes."""
from __future__ import annotations

from dataclasses import dataclass

from pyJianYingDraft.keyframe import KeyframeProperty

from shared.timeline_compiler import (
    CompiledKeyframe,
    slice_keyframes_for_window,
)


PROPERTY_MAP = {
    "position_x": KeyframeProperty.position_x,
    "position_y": KeyframeProperty.position_y,
    "scale_x": KeyframeProperty.scale_x,
    "scale_y": KeyframeProperty.scale_y,
    "rotation": KeyframeProperty.rotation,
    "opacity": KeyframeProperty.alpha,
}


@dataclass(frozen=True)
class LoweredKeyframe:
    property: str
    time: float
    value: float


def lower_keyframes_for_segment(
    *, semantic_keyframes: tuple[CompiledKeyframe, ...], semantic_duration: float,
    child_start: float, child_duration: float, warnings: list[str],
) -> tuple[LoweredKeyframe, ...]:
    del semantic_duration
    sliced = slice_keyframes_for_window(semantic_keyframes, child_start, child_duration)
    result = []
    for item in sliced:
        if item.property not in PROPERTY_MAP:
            warnings.append(f"JianYing does not support keyframe property: {item.property}")
            continue
        result.append(LoweredKeyframe(item.property, item.time, item.value))
    return tuple(result)


def convert_keyframe_value(property_name: str, value: float) -> float:
    if property_name in {"position_x", "position_y"}:
        return (float(value) - 0.5) * 2
    return float(value)


def apply_keyframes_to_video_segment(video_segment, keyframes: tuple[LoweredKeyframe, ...], warnings: list[str]) -> None:
    for item in keyframes:
        property_enum = PROPERTY_MAP.get(item.property)
        if property_enum is None:
            warnings.append(f"JianYing keyframe property unavailable: {item.property}")
            continue
        provider_value = convert_keyframe_value(item.property, item.value)
        try:
            video_segment.add_keyframe(property_enum, f"{item.time:g}s", provider_value)
        except Exception as error:
            raise RuntimeError(
                f"Failed to apply JianYing keyframe {item.property} at {item.time:g}s"
            ) from error
