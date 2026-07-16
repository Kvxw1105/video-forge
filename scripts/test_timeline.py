"""Tiny regression checks for VideoForge timeline behavior.
Run: python scripts/test_timeline.py
"""
from pathlib import Path
import sys
import tempfile
import subprocess
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.project_service import resolve_project_paths
from engines.renderer import _expand_segments_to_duration
from engines.voiceover import batch_sentences
from adapters.jianying import (
    _iter_bgm_tracks,
    _expand_segments_to_duration as jy_expand_segments_to_duration,
    _apply_cue_points as jy_apply_cue_points,
    _segment_chunks as _jy_segment_chunks,
    _audio_fade_seconds,
    generate_jianying_draft,
)
from routers.library import _project_asset_payload, _folder_matches


def test_jianying_audio_fade_seconds_are_clamped_to_segment_duration():
    assert _audio_fade_seconds({"fadeIn": 3, "fadeOut": 3}, 4.0) == (2.0, 2.0)
    assert _audio_fade_seconds({"fadeIn": 1, "fadeOut": 0.5}, 4.0) == (1.0, 0.5)


def test_library_folder_matches_nested_children():
    assert _folder_matches("国风素材库", "国风素材库")
    assert _folder_matches("国风素材库/子文件夹", "国风素材库")
    assert not _folder_matches("国风素材库2", "国风素材库")


def test_library_project_asset_payload_has_required_id_and_path():
    item = {"id": "lib_abc", "filename": "clip.mp4", "path": "D:/x/clip.mp4", "type": "video", "folder": "素材库"}
    payload = _project_asset_payload(item)
    assert payload["id"] == "lib_abc"
    assert payload["name"] == "clip.mp4"
    assert payload["path"] == "D:/x/clip.mp4"
    assert payload["type"] == "video"
    assert payload["metadata"]["libraryFolder"] == "素材库"


def test_voiceover_batches_do_not_exceed_hard_api_limit():
    long_text = "这是一段很长的文案，" * 40
    batches = batch_sentences([long_text], 250)
    assert len(batches) > 1
    assert all(len(x) <= 250 for x in batches), [len(x) for x in batches]


def test_voiceover_batches_keep_short_sentences_together():
    batches = batch_sentences(["第一句。", "第二句。", "第三句。"], 250)
    assert batches == ["第一句。第二句。第三句。"]


def test_resolve_project_paths_preserves_library_absolute_asset_paths():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        lib = root / "_library" / "clip.mp4"
        proj = root / "proj"
        lib.parent.mkdir(parents=True)
        proj.mkdir()
        lib.write_bytes(b"x")
        data = {"audio": {"voiceover": {}, "bgm": {}}, "segments": [{"assetPath": str(lib)}]}
        out = resolve_project_paths(proj, data)
        assert out["segments"][0]["assetPath"] == str(lib)


def test_resolve_project_paths_resolves_project_relative_asset_paths():
    with tempfile.TemporaryDirectory() as td:
        proj = Path(td) / "proj"
        asset = proj / "assets" / "a.png"
        asset.parent.mkdir(parents=True)
        asset.write_bytes(b"x")
        data = {"audio": {"voiceover": {}, "bgm": {}}, "segments": [{"assetPath": "assets/a.png"}]}
        out = resolve_project_paths(proj, data)
        assert Path(out["segments"][0]["assetPath"]).resolve() == asset.resolve()


def test_segments_loop_to_voiceover_duration():
    segments = [
        {"id": "a", "assetPath": "a.png", "type": "image", "start": 0, "end": 1},
        {"id": "b", "assetPath": "b.png", "type": "image", "start": 1, "end": 2},
    ]
    out = _expand_segments_to_duration(segments, 5.2)
    assert len(out) == 6, out
    assert out[0]["assetPath"] == "a.png"
    assert out[1]["assetPath"] == "b.png"
    assert out[2]["assetPath"] == "a.png"
    assert abs(out[-1]["end"] - 5.2) < 1e-6
    assert out[-1]["end"] - out[-1]["start"] <= 1.0


def test_segments_keep_order_without_loop_when_long_enough():
    segments = [
        {"id": "a", "assetPath": "a.png", "type": "image", "start": 0, "end": 2},
        {"id": "b", "assetPath": "b.png", "type": "image", "start": 2, "end": 4},
    ]
    out = _expand_segments_to_duration(segments, 3.0)
    assert [x["assetPath"] for x in out] == ["a.png", "b.png"], out
    assert out[-1]["end"] == 3.0


def test_jianying_segments_loop_to_voiceover_duration():
    segments = [
        {"id": "a", "assetPath": "a.png", "type": "image", "start": 0, "end": 1},
        {"id": "b", "assetPath": "b.png", "type": "image", "start": 1, "end": 2},
    ]
    out = jy_expand_segments_to_duration(segments, 5.2)
    assert len(out) == 6, out
    assert [x["assetPath"] for x in out[:4]] == ["a.png", "b.png", "a.png", "b.png"]
    assert abs(out[-1]["end"] - 5.2) < 1e-6


def test_jianying_applies_cue_points_before_looping():
    segments = [
        {"id": "a", "assetPath": "a.png", "type": "image", "start": 0, "end": 1},
        {"id": "b", "assetPath": "b.png", "type": "image", "start": 1, "end": 2},
    ]
    cues = [
        {"time": 0.0, "duration": 0.5},
        {"time": 0.5, "duration": 1.5},
    ]
    out = jy_apply_cue_points(segments, cues)
    assert [(x["assetPath"], x["start"], x["end"]) for x in out] == [
        ("a.png", 0.0, 0.5),
        ("b.png", 0.5, 2.0),
    ]


def test_jianying_draft_registers_bgm_audio_fade_material():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        img = root / "a.png"
        bgm = root / "b.mp3"
        out = root / "out"
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=64x64:d=0.1", "-frames:v", "1", str(img)], check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(bgm)], check=True, capture_output=True)
        draft = generate_jianying_draft({
            "name": "fade-test",
            "canvas": {"width": 64, "height": 64, "fps": 30, "background": {"value": "#000"}},
            "segments": [{"id": "s", "assetPath": str(img), "type": "image", "start": 0, "end": 2, "transform": {"x": 0.5, "y": 0.5, "scale": 1, "rotation": 0, "fit": "contain"}}],
            "audio": {"bgm": {"tracks": [{"file": str(bgm), "volume": 0.5, "trimStart": 0, "trimEnd": 2, "fadeIn": 0.5, "fadeOut": 0.5}]}, "voiceover": {}},
            "subtitles": [],
            "overlays": {"subtitle_enabled": True},
            "exportSettings": {"outputDir": str(out)},
        })
        data = json.loads((draft / "draft_content.json").read_text(encoding="utf-8"))
        fades = data["materials"]["audio_fades"]
        assert len(fades) == 1, fades
        assert fades[0]["fade_in_duration"] > 0
        assert fades[0]["fade_out_duration"] > 0


    segments = [
        {"id": "a", "assetPath": "a.png", "type": "image", "start": 0, "end": 1},
        {"id": "b", "assetPath": "b.png", "type": "image", "start": 1, "end": 2},
    ]
    cues = [
        {"time": 0.0, "duration": 0.5},
        {"time": 0.5, "duration": 1.5},
    ]
    out = jy_expand_segments_to_duration(jy_apply_cue_points(segments, cues), 4.0)
    assert [(x["assetPath"], round(x["start"], 2), round(x["end"], 2)) for x in out] == [
        ("a.png", 0.0, 0.5),
        ("b.png", 0.5, 2.0),
        ("a.png", 2.0, 2.5),
        ("b.png", 2.5, 4.0),
    ]


def test_jianying_splits_long_images_but_not_videos():
    segments = [
        {"id": "img", "assetPath": "a.png", "type": "image", "start": 0, "end": 7},
        {"id": "vid", "assetPath": "b.mp4", "type": "video", "start": 0, "end": 7},
    ]
    assert [round(x[1], 2) for x in _jy_segment_chunks(segments[0], image_limit=6.0)] == [6.0, 1.0]
    assert [round(x[1], 2) for x in _jy_segment_chunks(segments[1], image_limit=6.0)] == [7.0]


def test_bgm_tracks_prefer_multi_track_model():
    audio = {"bgm": {"file": "old.mp3", "volume": 0.1, "tracks": [
        {"file": "a.mp3", "volume": 0.2, "trimStart": 1, "trimEnd": 3},
        {"file": "b.mp3", "volume": 0.4, "trimStart": 0, "trimEnd": 0},
    ]}}
    tracks = list(_iter_bgm_tracks(audio))
    assert [t["file"] for t in tracks] == ["a.mp3", "b.mp3"]
    assert tracks[0]["trimStart"] == 1


def test_bgm_tracks_fallback_old_model():
    audio = {"bgm": {"file": "old.mp3", "volume": 0.3}}
    tracks = list(_iter_bgm_tracks(audio))
    assert tracks == [{"file": "old.mp3", "volume": 0.3, "trimStart": 0.0, "trimEnd": 0.0, "fadeIn": 0.0, "fadeOut": 0.0}]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
