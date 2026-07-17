import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.timeline_compiler import compile_project_timeline


def _project(asset_path: str, *, segments=None, voiceover_start=0, blocks=None):
    return {
        "id": "timeline_test",
        "canvas": {"width": 1080, "height": 1920, "fps": 30},
        "assets": [{"id": "asset_1", "type": "image", "path": asset_path}],
        "segments": segments if segments is not None else [
            {"id": "seg_1", "assetPath": asset_path, "type": "image", "start": 0, "end": 2}
        ],
        "audio": {"voiceovers": [], "bgm": {"tracks": []}, "sfx": []},
        "subtitles": [],
        "overlays": {},
        "timeline": {"voiceoverStartAt": voiceover_start, "blocks": blocks or []},
    }


def _times(compiled):
    return [(clip.start, clip.end) for clip in compiled.visual_clips]


def test_compile_is_deterministic_and_loops_without_cue_points(tmp_path):
    asset = tmp_path / "frame.png"
    asset.write_bytes(b"image")
    project = _project(str(asset))

    first = compile_project_timeline(project)
    second = compile_project_timeline(project)

    assert first == second
    assert _times(first) == [(0.0, 2.0), (2.0, 4.0), (4.0, 5.5)]


def test_cue_points_are_applied_once_before_looping(tmp_path):
    asset = tmp_path / "frame.png"
    asset.write_bytes(b"image")
    project = _project(str(asset))

    compiled = compile_project_timeline(
        project, cue_points=[{"time": 0, "duration": 1.5}]
    )

    assert _times(compiled) == [(0.0, 1.5), (1.5, 3.0), (3.0, 4.5), (4.5, 5.5)]


def test_last_clip_is_truncated_to_total_duration(tmp_path):
    asset = tmp_path / "frame.png"
    asset.write_bytes(b"image")

    compiled = compile_project_timeline(_project(str(asset)))

    assert compiled.visual_clips[-1].duration == 1.5
    assert compiled.visual_clips[-1].end == compiled.total_duration


def test_voiceover_start_offset_contributes_to_duration(tmp_path):
    asset = tmp_path / "frame.png"
    voice = tmp_path / "voice.mp3"
    asset.write_bytes(b"image")
    voice.write_bytes(b"audio")
    project = _project(str(asset), voiceover_start=3)
    project["audio"]["voiceovers"] = [
        {"id": "vo_1", "file": str(voice), "duration": 4, "isActive": True, "volume": 1}
    ]

    compiled = compile_project_timeline(project)

    assert compiled.total_duration == 7.5
    assert compiled.voiceover_clips[0].start == 3
    assert compiled.voiceover_clips[0].end == 7


def test_timeline_black_block_is_compiled(tmp_path):
    asset = tmp_path / "frame.png"
    asset.write_bytes(b"image")
    project = _project(
        str(asset),
        segments=[],
        blocks=[
            {"type": "black", "duration": 2, "bgColor": "#111111"},
            {"type": "assets", "duration": "rest", "source": "all", "mode": "ordered", "perAssetDuration": 2},
        ],
    )

    compiled = compile_project_timeline(project)

    assert compiled.visual_clips[0].media_type == "black"
    assert (compiled.visual_clips[0].start, compiled.visual_clips[0].end) == (0.0, 2.0)
    assert compiled.visual_clips[0].bg_color == "#111111"


def test_missing_asset_produces_warning_and_no_invalid_clip(tmp_path):
    missing = tmp_path / "missing.png"

    compiled = compile_project_timeline(_project(str(missing)))

    assert compiled.visual_clips == ()
    assert any("missing.png" in warning for warning in compiled.warnings)


def test_ffmpeg_and_jianying_share_compiler_and_visual_timing_payload(tmp_path):
    from adapters import jianying
    from engines import renderer

    asset = tmp_path / "frame.png"
    asset.write_bytes(b"image")
    compiled = compile_project_timeline(_project(str(asset)))

    ffmpeg_payload = compiled.visual_segments()
    jianying_payload = compiled.visual_segments()

    assert [(x["start"], x["end"]) for x in ffmpeg_payload] == [
        (x["start"], x["end"]) for x in jianying_payload
    ]
    assert renderer.compile_project_timeline is jianying.compile_project_timeline
    assert not hasattr(renderer, "_expand_segments_to_duration")
    assert not hasattr(jianying, "_expand_segments_to_duration")
    assert not hasattr(jianying, "_apply_cue_points")
