import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.project import Project
from shared.structured_composition import compile_structured_composition


def source_project(tmp_path, source_id, duration=3.0, color="a"):
    audio = tmp_path / f"{source_id}.wav"; audio.write_bytes(b"wav")
    image = tmp_path / f"{source_id}.png"; image.write_bytes(b"png")
    return {
        "id": source_id, "name": source_id, "canvas": {"width": 1080, "height": 1920, "ratio": "9:16", "fps": 30},
        "structuredContent": {"schemaVersion": 1, "episode": {"episodeId": f"ep_{source_id}", "title": source_id, "blocks": [{"id": "story", "type": "STORY", "text": source_id}], "variants": [{"id": "chapter", "name": "Chapter", "blockIds": ["story"]}], "activeVariantId": "chapter", "bindings": [{"blockId": "story", "audioSlice": {"voiceoverId": "vo", "sourceStart": 0, "sourceEnd": duration}, "visualAssetIds": ["image"], "subtitleIds": ["sub"]}]}},
        "assets": [{"id": "image", "type": "image", "name": f"{source_id}.png", "path": str(image)}],
        "audio": {"voiceovers": [{"id": "vo", "file": str(audio), "duration": duration}]},
        "subtitles": [{"id": "sub", "text": source_id, "start": 0.2, "end": min(1.0, duration)}],
        "overlays": {"title": {"enabled": True, "text": "source overlay"}, "directoryProgress": {"enabled": True}},
    }


def composition_project(items):
    return Project.model_validate({"id": "composition", "name": "Long Form", "canvas": {"width": 1080, "height": 1920, "ratio": "9:16", "fps": 30}, "templateId": "structured_composition", "composition": {"schemaVersion": 1, "compositionId": "longform_001", "title": "Long Form", "items": items}, "audio": {"bgm": {"file": "composition-bgm.wav"}, "sfx": []}, "overlays": {"title": {"text": "composition"}}})


def test_composition_model_round_trip_and_validation():
    project = composition_project([])
    assert Project.model_validate(project.model_dump()).composition.compositionId == "longform_001"
    with pytest.raises(ValueError):
        composition_project([{"id": "x", "sourceProjectId": "a", "variantId": "chapter", "chapterCardDuration": -1}])
    with pytest.raises(ValueError):
        composition_project([{"id": "x", "sourceProjectId": "a", "variantId": "chapter"}, {"id": "x", "sourceProjectId": "b", "variantId": "chapter"}])


def test_composition_compiles_order_cards_gaps_and_offsets(tmp_path):
    sources = {key: source_project(tmp_path, key, duration=value) for key, value in (("A", 3.0), ("B", 4.0), ("C", 2.0))}
    project = composition_project([
        {"id": "chapter_001", "sourceProjectId": "A", "variantId": "chapter", "chapterTitle": "第一章", "chapterCardDuration": 1.0, "gapAfter": 0.5},
        {"id": "chapter_002", "sourceProjectId": "B", "variantId": "chapter", "chapterTitle": "第二章", "chapterCardDuration": 1.0, "gapAfter": 0.5},
        {"id": "chapter_003", "sourceProjectId": "C", "variantId": "chapter", "chapterTitle": "第三章", "chapterCardDuration": 1.0, "gapAfter": 0.0},
    ])
    original = copy.deepcopy(project.model_dump())
    compiled = compile_structured_composition(project, lambda source_id: sources.get(source_id), lambda source_id, value: value, duration_resolver=lambda _: 4.0)
    assert [item.source_project_id for item in compiled.items] == ["A", "B", "C"]
    assert compiled.total_duration == 13.0
    assert compiled.project_view["name"].endswith("[composition]")
    assert len([segment for segment in compiled.project_view["segments"] if segment["type"] == "black"]) == 5
    assert compiled.project_view["audio"]["bgm"]["file"] == "composition-bgm.wav"
    assert all(segment["id"].startswith(("chapter_001__", "chapter_002__", "chapter_003__")) for segment in compiled.project_view["segments"])
    assert project.model_dump() == original


def test_composition_preserves_source_audio_ranges_and_offsets(tmp_path):
    sources = {key: source_project(tmp_path, key, duration=duration) for key, duration in (("A", 3.0), ("B", 4.0))}
    project = composition_project([{"id": "a", "sourceProjectId": "A", "variantId": "chapter", "gapAfter": 0.5}, {"id": "b", "sourceProjectId": "B", "variantId": "chapter"}])
    compiled = compile_structured_composition(project, lambda source_id: sources.get(source_id), lambda source_id, value: value, duration_resolver=lambda path: 3.0 if Path(path).stem == "A" else 4.0)
    clips = compiled.project_view["audio"]["voiceoverSegments"]
    assert clips[0]["trimStart"] == 0
    assert clips[0]["trimEnd"] == 3
    assert clips[0]["startAt"] == 0
    assert clips[1]["startAt"] == 3.5
    assert clips[1]["trimStart"] == 0
    assert clips[1]["trimEnd"] == 4
    assert all(clip["id"].startswith(("a__", "b__")) for clip in clips)
    assert all(sub["id"].startswith(("a__", "b__")) for sub in compiled.project_view["subtitles"])


@pytest.mark.parametrize("bad", ["missing", "legacy"])
def test_invalid_sources_are_controlled_errors(tmp_path, bad):
    project = composition_project([{"id": "x", "sourceProjectId": "missing", "variantId": "chapter"}])
    sources = {} if bad == "missing" else {"missing": {"id": "missing"}}
    with pytest.raises(ValueError):
        compile_structured_composition(project, lambda source_id: sources.get(source_id), lambda source_id, value: value)
