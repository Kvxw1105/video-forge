import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.structured_content import compile_structured_media_variant
from shared.timeline_compiler import compile_project_timeline
from test_structured_content import _structured_project


def _project(tmp_path: Path):
    audio = tmp_path / "master.wav"
    image = tmp_path / "frame.png"
    audio.write_bytes(b"audio")
    image.write_bytes(b"image")
    blocks = [
        {"id": "hook", "type": "HOOK", "text": "Hook"},
        {"id": "story", "type": "STORY", "text": "Story"},
        {"id": "outro", "type": "SHORT_OUTRO", "text": "Outro"},
    ]
    return {
        "id": "p1", "name": "Structured",
        "structuredContent": {"schemaVersion": 1, "episode": {
            "episodeId": "ep1", "title": "Episode", "blocks": blocks,
            "variants": [
                {"id": "publish", "name": "Publish", "blockIds": ["hook", "story", "outro"]},
                {"id": "master", "name": "Master", "blockIds": ["story"]},
                {"id": "chapter", "name": "Chapter", "blockIds": ["hook", "story"]},
            ], "activeVariantId": "publish",
            "bindings": [
                {"blockId": "hook", "audioSlice": {"voiceoverId": "master", "sourceStart": 0, "sourceEnd": 2}, "visualAssetIds": ["img"], "subtitleIds": ["s1"]},
                {"blockId": "story", "audioSlice": {"voiceoverId": "master", "sourceStart": 2, "sourceEnd": 7}, "visualAssetIds": ["img"], "subtitleIds": ["s2"]},
                {"blockId": "outro", "duration": 1.5, "visualAssetIds": []},
            ],
        }},
        "audio": {"voiceovers": [{"id": "master", "file": str(audio), "duration": 7.0}]},
        "assets": [{"id": "img", "type": "image", "name": "frame.png", "path": str(image)}],
        "subtitles": [
            {"id": "s1", "text": "one", "start": 0.2, "end": 1.5},
            {"id": "s2", "text": "two", "start": 2.2, "end": 6.5},
        ],
    }


def test_variant_compiles_ranges_and_reuses_audio_probe(tmp_path):
    project = _project(tmp_path)
    calls = []
    result = compile_structured_media_variant(project, "publish", duration_resolver=lambda p: calls.append(p) or 7.0)
    assert [w.block_id for w in result.block_windows] == ["hook", "story", "outro"]
    assert [round(w.duration, 3) for w in result.block_windows] == [2.0, 5.0, 1.5]
    assert [(c["trimStart"], c["trimEnd"]) for c in result.project_view["audio"]["voiceoverSegments"]] == [(0.0, 2.0), (2.0, 7.0)]
    assert len(calls) == 1


def test_variant_is_deterministic_and_does_not_mutate_input(tmp_path):
    project = _project(tmp_path)
    before = copy.deepcopy(project)
    first = compile_structured_media_variant(project, "master", duration_resolver=lambda _: 7.0)
    second = compile_structured_media_variant(project, "master", duration_resolver=lambda _: 7.0)
    assert first == second
    assert project == before
    assert first.total_duration == 5.0


def test_missing_visual_uses_black_fallback_warning(tmp_path):
    project = _project(tmp_path)
    project["structuredContent"]["episode"]["bindings"][0]["visualAssetIds"] = ["missing"]
    result = compile_structured_media_variant(project, "publish", duration_resolver=lambda _: 7.0)
    assert result.project_view["segments"][0]["type"] == "black"
    assert any("visual asset not found" in warning for warning in result.warnings)


def test_timeline_expands_compiled_voiceover_segments(tmp_path):
    result = compile_structured_media_variant(_project(tmp_path), "publish", duration_resolver=lambda _: 7.0)
    timeline = compile_project_timeline(result.project_view, duration_resolver=lambda _: 7.0)
    assert [(round(c.start, 3), round(c.duration, 3), round(c.source_start, 3)) for c in timeline.voiceover_clips] == [(0.0, 2.0, 0.0), (2.0, 5.0, 2.0)]
    assert timeline.total_duration >= result.total_duration


@pytest.mark.parametrize("variant, expected", [("master", ["story"]), ("publish", ["hook", "story", "outro"])])
def test_variant_block_selection(variant, expected, tmp_path):
    result = compile_structured_media_variant(_project(tmp_path), variant, duration_resolver=lambda _: 7.0)
    assert [window.block_id for window in result.block_windows] == expected


def test_full_eight_block_variants_preserve_source_ranges(tmp_path):
    project = _structured_project()
    audio = tmp_path / "master.wav"; audio.write_bytes(b"wav")
    image = tmp_path / "frame.png"; image.write_bytes(b"png")
    project["audio"] = {"voiceovers": [{"id": "master", "file": str(audio), "duration": 32}]}
    project["assets"] = [{"id": "img", "name": "frame.png", "type": "image", "path": str(image)}]
    ranges = [(0, 4), (4, 7), (7, 10), (10, 18), (18, 25), (25, 27), (27, 30), (30, 32)]
    ids = ["hook_01", "cta_01", "bridge_in_01", "story_01", "mechanism_01", "judgment_01", "short_outro_01", "bridge_out_01"]
    project["structuredContent"]["episode"]["bindings"] = [
        {"blockId": block_id, "audioSlice": {"voiceoverId": "master", "sourceStart": start, "sourceEnd": end}, "visualAssetIds": ["img"]}
        for block_id, (start, end) in zip(ids, ranges)
    ]
    publish = compile_structured_media_variant(project, "publish", duration_resolver=lambda _: 32)
    master = compile_structured_media_variant(project, "master", duration_resolver=lambda _: 32)
    chapter = compile_structured_media_variant(project, "chapter", duration_resolver=lambda _: 32)
    assert [w.block_id for w in publish.block_windows] == ["hook_01", "cta_01", "story_01", "mechanism_01", "judgment_01", "short_outro_01"]
    assert [w.block_id for w in master.block_windows] == ["story_01", "mechanism_01", "judgment_01"]
    assert [w.block_id for w in chapter.block_windows] == ["bridge_in_01", "story_01", "mechanism_01", "judgment_01", "bridge_out_01"]
    assert [c["trimStart"] for c in master.project_view["audio"]["voiceoverSegments"]] == [10.0, 18.0, 25.0]
    assert master.total_duration == 17.0
    assert chapter.total_duration == 22.0
