import sys
import logging
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

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


def test_absolute_cue_gap_is_materialized_and_looped_with_unique_ids(tmp_path):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    first.write_bytes(b"image")
    second.write_bytes(b"image")
    project = _project(str(first), segments=[
        {"id": "first", "assetPath": str(first), "type": "image", "start": 0, "end": 1},
        {"id": "second", "assetPath": str(second), "type": "image", "start": 1, "end": 2},
    ])

    compiled = compile_project_timeline(project, cue_points=[
        {"time": 0, "duration": 1},
        {"time": 3, "duration": 1},
    ])

    assert [(c.media_type, c.start, c.end) for c in compiled.visual_clips] == [
        ("image", 0.0, 1.0),
        ("black", 1.0, 3.0),
        ("image", 3.0, 4.0),
        ("image", 4.0, 5.0),
        ("black", 5.0, 5.5),
    ]
    assert len({clip.id for clip in compiled.visual_clips}) == len(compiled.visual_clips)


def test_overlapping_or_reversed_cues_are_clamped_with_stable_warning(tmp_path):
    asset = tmp_path / "frame.png"
    asset.write_bytes(b"image")
    project = _project(str(asset), segments=[
        {"id": "a", "assetPath": str(asset), "type": "image", "start": 0, "end": 2},
        {"id": "b", "assetPath": str(asset), "type": "image", "start": 2, "end": 4},
    ])

    compiled = compile_project_timeline(project, cue_points=[
        {"time": 2, "duration": 2},
        {"time": 1, "duration": 1},
    ])

    assert [(c.media_type, c.start, c.end) for c in compiled.visual_clips[:3]] == [
        ("black", 0.0, 2.0), ("image", 2.0, 4.0), ("image", 4.0, 5.0)
    ]
    assert any("clamped" in warning for warning in compiled.warnings)
    assert all(a.end <= b.start for a, b in zip(compiled.visual_clips, compiled.visual_clips[1:]))


def test_numeric_last_cue_uses_natural_duration_for_total_end(tmp_path):
    asset = tmp_path / "frame.png"
    asset.write_bytes(b"image")
    project = _project(str(asset), segments=[
        {"id": "a", "assetPath": str(asset), "type": "image", "start": 0, "end": 2},
        {"id": "b", "assetPath": str(asset), "type": "image", "start": 2, "end": 4},
    ])

    compiled = compile_project_timeline(project, cue_points=[0, 10])

    assert compiled.total_duration == 12.5
    assert _times(compiled)[:2] == [(0.0, 6.0), (6.0, 10.0)]
    assert any(clip.start == 10 and clip.end == 12 for clip in compiled.visual_clips)


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


def test_fixed_timeline_blocks_contribute_their_full_duration(tmp_path):
    asset = tmp_path / "frame.png"
    asset.write_bytes(b"image")
    project = _project(str(asset), segments=[], blocks=[
        {"type": "black", "duration": 4},
        {"type": "assets", "duration": 6, "source": "all", "mode": "ordered", "perAssetDuration": 2},
    ])

    compiled = compile_project_timeline(project)

    assert compiled.total_duration == 10.5
    assert compiled.visual_clips[-1].end == 10.5


def test_empty_block_pool_keeps_interval_as_black_fallback(tmp_path):
    project = _project(str(tmp_path / "missing.png"), segments=[], blocks=[
        {"type": "assets", "duration": 4, "source": "images", "mode": "ordered"},
    ])

    compiled = compile_project_timeline(project)

    assert compiled.visual_clips[0].media_type == "black"
    assert (compiled.visual_clips[0].start, compiled.visual_clips[0].end) == (0.0, 4.0)
    assert any("block" in warning.lower() for warning in compiled.warnings)


def test_valid_legacy_segments_take_precedence_over_timeline_blocks(tmp_path):
    asset = tmp_path / "frame.png"
    asset.write_bytes(b"image")
    project = _project(str(asset), blocks=[{"type": "black", "duration": 4}])

    compiled = compile_project_timeline(project)

    assert compiled.visual_clips[0].media_type == "image"


def test_missing_asset_produces_warning_and_no_invalid_clip(tmp_path):
    missing = tmp_path / "missing.png"

    compiled = compile_project_timeline(_project(str(missing)))

    assert compiled.visual_clips == ()
    assert any("missing.png" in warning for warning in compiled.warnings)


def test_unsupported_existing_asset_is_excluded_and_does_not_extend_duration(tmp_path):
    archive = tmp_path / "payload.zip"
    archive.write_bytes(b"zip")
    project = _project(str(archive), segments=[
        {"id": "bad", "assetPath": str(archive), "type": "image", "start": 0, "end": 60}
    ])

    compiled = compile_project_timeline(project)

    assert compiled.visual_clips == ()
    assert compiled.total_duration == 5.5
    assert any("Unsupported visual asset" in warning for warning in compiled.warnings)


def test_real_audio_duration_wins_and_zero_volume_is_preserved(tmp_path):
    asset = tmp_path / "frame.png"
    voice = tmp_path / "voice.mp3"
    asset.write_bytes(b"image")
    voice.write_bytes(b"audio")
    project = _project(str(asset))
    project["audio"]["voiceovers"] = [{
        "id": "vo", "file": str(voice), "duration": 20, "volume": 0, "isActive": True
    }]

    compiled = compile_project_timeline(project, duration_resolver=lambda _path: 4)

    assert compiled.voiceover_clips[0].duration == 4
    assert compiled.voiceover_clips[0].volume == 0
    assert compiled.total_duration == 5.5


def test_duration_resolver_failure_warns_and_falls_back_to_declared(tmp_path):
    asset = tmp_path / "frame.png"
    voice = tmp_path / "voice.mp3"
    asset.write_bytes(b"image")
    voice.write_bytes(b"audio")
    project = _project(str(asset))
    project["audio"]["voiceovers"] = [{
        "id": "vo", "file": str(voice), "duration": 3, "volume": 1, "isActive": True
    }]

    def fail(_path):
        raise RuntimeError("probe failed")

    compiled = compile_project_timeline(project, duration_resolver=fail)

    assert compiled.voiceover_clips[0].duration == 3
    assert any("probe failed" in warning for warning in compiled.warnings)


def test_bgm_and_sfx_share_actual_duration_and_volume_rules(tmp_path):
    asset = tmp_path / "frame.png"
    bgm = tmp_path / "bgm.mp3"
    sfx = tmp_path / "sfx.wav"
    asset.write_bytes(b"image")
    bgm.write_bytes(b"audio")
    sfx.write_bytes(b"audio")
    project = _project(str(asset))
    project["audio"]["bgm"] = {
        "tracks": [{"file": str(bgm), "duration": 20, "volume": 2}]
    }
    project["audio"]["sfx"] = [
        {"file": str(sfx), "duration": 20, "volume": -1}
    ]
    actual = {str(bgm): 3, str(sfx): 2}

    compiled = compile_project_timeline(
        project, duration_resolver=lambda path: actual[path]
    )

    assert compiled.bgm_clips[0].duration == 3
    assert compiled.bgm_clips[0].volume == 1
    assert compiled.sfx_clips[0].duration == 2
    assert compiled.sfx_clips[0].volume == 0


def test_compiler_does_not_mutate_project(tmp_path):
    asset = tmp_path / "frame.png"
    asset.write_bytes(b"image")
    project = _project(str(asset))
    original = deepcopy(project)

    compile_project_timeline(project, cue_points=[{"time": 1, "duration": 1}])

    assert project == original


def test_ffmpeg_and_jianying_share_compiler_and_visual_timing_payload(tmp_path):
    from adapters import jianying
    from engines import renderer

    asset = tmp_path / "frame.png"
    asset.write_bytes(b"image")
    compiled = compile_project_timeline(_project(str(asset)))

    assert renderer.compile_project_timeline is jianying.compile_project_timeline
    assert not hasattr(renderer, "_expand_segments_to_duration")
    assert not hasattr(jianying, "_expand_segments_to_duration")
    assert not hasattr(jianying, "_apply_cue_points")


def test_ffmpeg_renderer_logs_compiler_warnings_once(monkeypatch, tmp_path, caplog):
    from engines import renderer

    project = _project(str(tmp_path / "missing.png"))
    real_compile = compile_project_timeline
    compile_calls = 0

    def tracked_compile(*args, **kwargs):
        nonlocal compile_calls
        compile_calls += 1
        return real_compile(*args, **kwargs)

    def fake_run(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"video")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(renderer, "compile_project_timeline", tracked_compile)
    monkeypatch.setattr(renderer, "_run_cmd", fake_run)

    with caplog.at_level(logging.WARNING):
        renderer.render_preview(project, tmp_path / "preview.mp4")

    assert compile_calls == 1
    assert "Missing visual asset" in caplog.text
