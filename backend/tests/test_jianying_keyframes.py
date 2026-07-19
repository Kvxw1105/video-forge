import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.jianying_keyframes import (
    apply_keyframes_to_video_segment,
    convert_keyframe_value,
    lower_keyframes_for_segment,
)
from shared.timeline_compiler import CompiledKeyframe, interpolate_keyframe_value, slice_keyframes_for_window


def _keys():
    return (
        CompiledKeyframe("scale_x", 0.0, 1.0),
        CompiledKeyframe("scale_x", 5.0, 1.2),
        CompiledKeyframe("scale_x", 10.0, 0.8),
        CompiledKeyframe("scale_x", 14.0, 1.0),
        CompiledKeyframe("rotation", 0.0, 0.0),
        CompiledKeyframe("rotation", 7.0, 15.0),
        CompiledKeyframe("rotation", 14.0, -10.0),
        CompiledKeyframe("opacity", 0.0, 1.0),
        CompiledKeyframe("opacity", 7.0, 0.5),
        CompiledKeyframe("opacity", 14.0, 1.0),
    )


def test_linear_interpolation_handles_boundaries_and_gaps():
    keys = _keys()
    assert interpolate_keyframe_value(keys, "scale_x", -1) == 1.0
    assert interpolate_keyframe_value(keys, "scale_x", 6) == pytest.approx(1.12)
    assert interpolate_keyframe_value(keys, "scale_x", 14) == 1.0
    assert interpolate_keyframe_value(keys, "missing", 2) is None


def test_shared_slice_adds_interpolated_window_boundaries():
    keys = (CompiledKeyframe("scale_x", 0, 1), CompiledKeyframe("scale_x", 10, 2))
    sliced = slice_keyframes_for_window(keys, 0, 6)
    assert [(item.time, item.value) for item in sliced] == [(0.0, 1.0), (6.0, 1.6)]


def test_position_values_convert_from_canonical_canvas_coordinates():
    assert convert_keyframe_value("position_x", 0.0) == -1.0
    assert convert_keyframe_value("position_x", 0.5) == 0.0
    assert convert_keyframe_value("position_x", 1.0) == 1.0
    assert convert_keyframe_value("position_y", 0.5) == 0.0


def test_lowering_preserves_boundary_state_for_each_six_second_child():
    warnings = []
    lowered = lower_keyframes_for_segment(
        semantic_keyframes=_keys(), semantic_duration=14, child_start=6, child_duration=6, warnings=warnings
    )
    scale = [(item.time, item.value) for item in lowered if item.property == "scale_x"]
    assert scale[0][0] == 0.0
    assert scale[0][1] == pytest.approx(1.12)
    assert scale[-1][0] == 6.0
    assert scale[-1][1] == pytest.approx(0.9)
    assert not warnings


def test_apply_keyframes_uses_provider_mapping_and_local_times():
    class FakeSegment:
        def __init__(self):
            self.calls = []

        def add_keyframe(self, property_name, time, value):
            self.calls.append((property_name, time, value))

    target = FakeSegment()
    warnings = []
    apply_keyframes_to_video_segment(
        target,
        lower_keyframes_for_segment(
            semantic_keyframes=(CompiledKeyframe("position_x", 0, 0.5), CompiledKeyframe("position_x", 6, 1.0)),
            semantic_duration=6, child_start=0, child_duration=6, warnings=warnings,
        ),
        warnings,
    )
    assert [(call[0].name, call[1], call[2]) for call in target.calls] == [("position_x", "0s", 0.0), ("position_x", "6s", 1.0)]
