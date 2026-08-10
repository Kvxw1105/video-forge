from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import project_service
from services.image_generation_service import create_batch, get_batch
from shared.visual_scene import visual_source_hash


def _timed_project(tmp_path, monkeypatch):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    project = project_service.create_project("Timed image scenes", "9:16")
    subtitles = [
        {"id": "s1", "text": "雨夜里，旅人走进车站。", "start": 0.0, "end": 1.5},
        {"id": "s2", "text": "灯光照亮他的侧脸。", "start": 1.5, "end": 3.25},
    ]
    structured = {
        "schemaVersion": 1,
        "episode": {
            "episodeId": "episode_1",
            "blocks": [
                {"id": "story", "type": "STORY", "text": subtitles[0]["text"]},
                {"id": "method", "type": "METHOD", "text": subtitles[1]["text"]},
            ],
            "variants": [
                {"id": "publish", "name": "Publish", "blockIds": ["story", "method"]},
            ],
            "activeVariantId": "publish",
            "bindings": [
                {"blockId": "story", "duration": 1.5, "subtitleIds": ["s1"]},
                {"blockId": "method", "duration": 1.75, "subtitleIds": ["s2"]},
            ],
        },
    }
    project = project_service.update_project(
        project.id,
        {"subtitles": subtitles, "structuredContent": structured},
    )
    project_dict = project.model_dump()
    plan = {
        "schemaVersion": 1,
        "planId": "plan_1",
        "sourceHash": visual_source_hash(project_dict),
        "scenes": [
            {
                "id": "scene_1",
                "blockId": "story",
                "subtitleIds": ["s1"],
                "summary": "雨夜车站中的旅人",
                "prompt": "cinematic traveler entering a rainy station",
            },
            {
                "id": "scene_2",
                "blockId": "method",
                "subtitleIds": ["s2"],
                "summary": "暖光中的侧脸",
                "prompt": "warm station light across a traveler's profile",
            },
        ],
        "settings": {"mode": "fixed_units", "unitsPerScene": 1},
    }
    return project_service.update_project(
        project.id,
        {
            "structuredContent": {
                **project.structuredContent.model_dump(),
                "episode": {
                    **project.structuredContent.episode.model_dump(),
                    "visualPlan": plan,
                },
            }
        },
    )


def test_agent_batch_uses_subtitle_timing_and_persists(tmp_path, monkeypatch):
    project = _timed_project(tmp_path, monkeypatch)

    batch = create_batch(
        project.id,
        channel="agent",
        style_anchor="low-saturation mid-century cinema",
        continuity_anchor="same traveler in a charcoal coat",
    )

    assert batch["status"] == "awaiting_agent"
    assert batch["visualPlanId"] == "plan_1"
    assert batch["visualSourceHash"] == project.structuredContent.episode.visualPlan.sourceHash
    assert [item["sceneId"] for item in batch["items"]] == ["scene_1", "scene_2"]
    assert batch["items"][0]["start"] == 0.0
    assert batch["items"][0]["end"] == 1.5
    assert batch["items"][1]["duration"] == 1.75
    assert len(batch["items"][0]["inputHash"]) == 64
    assert "low-saturation" in batch["items"][0]["finalPrompt"]
    assert "charcoal coat" in batch["items"][1]["finalPrompt"]

    reloaded = get_batch(project.id, batch["batchId"])
    assert reloaded == batch
    assert (
        tmp_path
        / project.id
        / "image-generation"
        / "batches"
        / f"{batch['batchId']}.json"
    ).is_file()
