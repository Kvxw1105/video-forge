from copy import deepcopy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.timeline_compiler import _expand_visuals, compile_project_timeline


def _project(tmp_path, keyframes=None, duration=14):
    asset = tmp_path / "frame.png"
    asset.write_bytes(b"png")
    segment = {"id": "clip_1", "assetPath": str(asset), "type": "image", "start": 0, "end": duration}
    if keyframes is not None:
        segment["keyframes"] = keyframes
    return {"name": "keyframes", "canvas": {"width": 1080, "height": 1920, "fps": 30}, "segments": [segment]}


def test_compiler_normalizes_six_visual_properties_to_clip_local_seconds(tmp_path):
    raw = [
        {"property": "position_x", "time": 0, "value": 0.5},
        {"property": "position_y", "time": 14, "value": 0.65},
        {"property": "scale_x", "time": 0, "value": 1.0},
        {"property": "scale_x", "time": 5, "value": 1.2},
        {"property": "scale_x", "time": 10, "value": 0.8},
        {"property": "scale_x", "time": 14, "value": 1.0},
        {"property": "scale_y", "time": 0, "value": 1.0},
        {"property": "rotation", "time": 7, "value": 15},
        {"property": "opacity", "time": 7, "value": 0.5},
    ]
    compiled = compile_project_timeline(_project(tmp_path, raw))
    clip = compiled.visual_clips[0]
    assert [(item.property, item.time, item.value) for item in clip.keyframes] == [
        ("opacity", 7.0, 0.5), ("position_x", 0.0, 0.5),
        ("position_y", 14.0, 0.65), ("rotation", 7.0, 15.0),
        ("scale_x", 0.0, 1.0), ("scale_x", 5.0, 1.2),
        ("scale_x", 10.0, 0.8), ("scale_x", 14.0, 1.0),
        ("scale_y", 0.0, 1.0),
    ]


def test_compiler_ignores_invalid_keyframes_with_warnings_and_does_not_mutate_project(tmp_path):
    raw = [
        {"property": "blur", "time": 1, "value": 1},
        {"property": "scale_x", "time": -1, "value": 1},
        {"property": "scale_x", "time": "nan", "value": 1},
        {"property": "scale_x", "time": 15, "value": 1},
        {"property": "scale_x", "time": 1, "value": 0},
        {"property": "opacity", "time": 2, "value": 1.5},
        {"property": "rotation", "time": 3, "value": "bad"},
        {"property": "scale_y", "time": 4, "value": 1, "easing": "easeIn"},
    ]
    project = _project(tmp_path, raw)
    before = deepcopy(project)
    compiled = compile_project_timeline(project)
    assert project == before
    assert [(item.property, item.time, item.value) for item in compiled.visual_clips[0].keyframes] == [("opacity", 2.0, 1.0), ("scale_y", 4.0, 1.0)]
    assert len(compiled.warnings) >= 7
    assert any("unsupported keyframe property" in warning for warning in compiled.warnings)
    assert any("time" in warning for warning in compiled.warnings)
    assert any("scale_x" in warning and "positive" in warning for warning in compiled.warnings)
    assert any("opacity" in warning and "clamped" in warning for warning in compiled.warnings)
    assert any("easing" in warning for warning in compiled.warnings)


def test_duplicate_property_and_time_uses_last_valid_value_and_sort_is_stable(tmp_path):
    raw = [
        {"property": "rotation", "time": 2, "value": 10},
        {"property": "rotation", "time": 2.0000000001, "value": 20},
        {"property": "rotation", "time": 1, "value": 5},
    ]
    clip = compile_project_timeline(_project(tmp_path, raw)).visual_clips[0]
    assert [(item.time, item.value) for item in clip.keyframes] == [(1.0, 5.0), (2.0, 20.0)]


def test_truncating_repeated_visual_clip_removes_keyframes_past_new_end(tmp_path):
    raw = [
        {"property": "scale_x", "time": 0, "value": 1},
        {"property": "scale_x", "time": 5, "value": 1.2},
        {"property": "scale_x", "time": 10, "value": 0.8},
        {"property": "scale_x", "time": 14, "value": 1},
    ]
    asset = tmp_path / "frame.png"
    asset.write_bytes(b"png")
    pattern = [{"id": "clip_1", "assetPath": str(asset), "type": "image", "start": 0, "end": 14, "keyframes": raw}]
    compiled = _expand_visuals(pattern, 20, [])
    assert len(compiled) == 2
    assert compiled[1].start == 14.0
    assert compiled[1].keyframes[-1].time <= compiled[1].duration
