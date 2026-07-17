"""Lower provider-neutral visual keyframes to JianYing segment keyframes."""
from __future__ import annotations

from dataclasses import dataclass

from pyJianYingDraft.keyframe import KeyframeProperty

from shared.timeline_compiler import CompiledKeyframe


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


def seconds_to_jianying_time(seconds: float) -> int:
    return round(float(seconds) * 1_000_000)


def interpolate_linear(
    keyframes: tuple[CompiledKeyframe, ...], property_name: str, at_time: float,
) -> float | None:
    points = sorted((item for item in keyframes if item.property == property_name), key=lambda item: item.time)
    if not points:
        return None
    if at_time <= points[0].time:
        return points[0].value
    if at_time >= points[-1].time:
        return points[-1].value
    for left, right in zip(points, points[1:]):
        if left.time <= at_time <= right.time:
            if right.time == left.time:
                return right.value
            ratio = (at_time - left.time) / (right.time - left.time)
            return left.value + ratio * (right.value - left.value)
    return points[-1].value


def lower_keyframes_for_segment(
    *, semantic_keyframes: tuple[CompiledKeyframe, ...], semantic_duration: float,
    child_start: float, child_duration: float, warnings: list[str],
) -> tuple[LoweredKeyframe, ...]:
    del semantic_duration  # the compiler has already validated the semantic window
    child_end = child_start + child_duration
    result: dict[tuple[str, float], LoweredKeyframe] = {}
    for property_name in dict.fromkeys(item.property for item in semantic_keyframes):
        if property_name not in PROPERTY_MAP:
            warnings.append(f"JianYing does not support keyframe property: {property_name}")
            continue
        points = [item for item in semantic_keyframes if item.property == property_name]
        if any(item.easing != "linear" for item in points):
            warnings.append(f"JianYing lowering uses linear easing for {property_name}")
        for semantic_time in (child_start, child_end):
            value = interpolate_linear(tuple(points), property_name, semantic_time)
            if value is not None:
                local_time = round(semantic_time - child_start, 6)
                result[(property_name, local_time)] = LoweredKeyframe(property_name, local_time, value)
        for item in points:
            if child_start < item.time < child_end:
                local_time = round(item.time - child_start, 6)
                result[(property_name, local_time)] = LoweredKeyframe(property_name, local_time, item.value)
    return tuple(sorted(result.values(), key=lambda item: (item.property, item.time)))


def apply_keyframes_to_video_segment(video_segment, keyframes: tuple[LoweredKeyframe, ...], warnings: list[str]) -> None:
    for item in keyframes:
        property_enum = PROPERTY_MAP.get(item.property)
        if property_enum is None:
            warnings.append(f"JianYing keyframe property unavailable: {item.property}")
            continue
        video_segment.add_keyframe(property_enum, f"{item.time:g}s", item.value)
