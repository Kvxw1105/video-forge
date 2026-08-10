from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import image_generation_service, project_service
from services.project_service import resolve_project_paths
from shared.structured_content import compile_structured_media_variant
from shared.timeline_compiler import compile_project_timeline
from shared.visual_scene import visual_source_hash


_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP4z8DwHwAF"
    "AAH/iZk9HQAAAABJRU5ErkJggg=="
)


def _project(tmp_path, monkeypatch):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    project = project_service.create_project("Narration timed AI images")
    subtitles = [
        {"id": "s1", "text": "第一幕。", "start": 0.0, "end": 1.5},
        {"id": "s2", "text": "第二幕。", "start": 1.5, "end": 3.25},
    ]
    structured = {
        "schemaVersion": 1,
        "episode": {
            "episodeId": "episode_e2e",
            "blocks": [
                {"id": "story", "type": "STORY", "text": "第一幕。"},
                {"id": "method", "type": "METHOD", "text": "第二幕。"},
            ],
            "variants": [{"id": "publish", "name": "Publish", "blockIds": ["story", "method"]}],
            "activeVariantId": "publish",
            "bindings": [
                {"blockId": "story", "duration": 1.5, "subtitleIds": ["s1"]},
                {"blockId": "method", "duration": 1.75, "subtitleIds": ["s2"]},
            ],
        },
    }
    project = project_service.update_project(project.id, {"subtitles": subtitles, "structuredContent": structured})
    plan = {
        "schemaVersion": 1,
        "planId": "plan_e2e",
        "sourceHash": visual_source_hash(project.model_dump()),
        "scenes": [
            {"id": "scene_1", "blockId": "story", "subtitleIds": ["s1"], "prompt": "first scene"},
            {"id": "scene_2", "blockId": "method", "subtitleIds": ["s2"], "prompt": "second scene"},
        ],
        "settings": {},
    }
    return project_service.update_project(
        project.id,
        {"structuredContent": {**project.structuredContent.model_dump(), "episode": {**project.structuredContent.episode.model_dump(), "visualPlan": plan}}},
    )


def test_agent_images_compile_to_exact_narration_windows(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    batch = image_generation_service.create_batch(project.id, channel="agent", provider_id="codex-imagegen")
    selections = []
    for item in batch["items"]:
        candidate = image_generation_service.upload_agent_candidate(
            project.id, batch["batchId"], item["sceneId"], item["inputHash"], _PNG
        )
        selections.append({"sceneId": item["sceneId"], "candidateId": candidate["candidateId"]})
    result = image_generation_service.approve_candidates(project.id, batch["batchId"], selections)
    assert result["batch"]["status"] == "succeeded"

    stored = project_service.get_project(project.id)
    resolved = resolve_project_paths(tmp_path / project.id, stored.model_dump())
    compiled = compile_structured_media_variant(resolved, "publish", duration_resolver=lambda _: 3.25)
    assert [(row["start"], row["end"]) for row in compiled.project_view["segments"]] == [
        (0.0, 1.5),
        (1.5, 3.25),
    ]
    assert [row["metadata"]["sceneId"] for row in compiled.project_view["segments"]] == [
        "scene_1",
        "scene_2",
    ]
    assert all(Path(row["assetPath"]).is_file() for row in compiled.project_view["segments"])

    timeline = compile_project_timeline(compiled.project_view, duration_resolver=lambda _: 3.25)
    # The canonical timeline keeps the renderer's established 5-second minimum
    # by looping visuals only after the narration-timed Scene windows.
    assert [(clip.start, clip.end) for clip in timeline.visual_clips[:2]] == [(0.0, 1.5), (1.5, 3.25)]
    assert timeline.visual_clips[2].start == 3.25
    assert timeline.visual_clips[-1].end == 5.0
    assert timeline.total_duration == 5.5
