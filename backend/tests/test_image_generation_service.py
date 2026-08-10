from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import project_service
import base64

import pytest

from services.image_generation_service import (
    ImageGenerationError,
    approve_candidates,
    create_batch,
    get_batch,
    record_item_failure,
    retry_failed_items,
    upload_agent_candidate,
)
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


_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP4z8DwHwAF"
    "AAH/iZk9HQAAAABJRU5ErkJggg=="
)


def test_agent_upload_is_idempotent_and_approval_binds_provenance(tmp_path, monkeypatch):
    project = _timed_project(tmp_path, monkeypatch)
    batch = create_batch(project.id, channel="agent", provider_id="codex-imagegen")
    item = batch["items"][0]
    image = tmp_path / "generated.png"
    image.write_bytes(_PNG)

    candidate = upload_agent_candidate(
        project.id, batch["batchId"], item["sceneId"], item["inputHash"], image
    )
    duplicate = upload_agent_candidate(
        project.id, batch["batchId"], item["sceneId"], item["inputHash"], image
    )

    assert duplicate["candidateId"] == candidate["candidateId"]
    assert duplicate["contentHash"] == candidate["contentHash"]
    result = approve_candidates(
        project.id,
        batch["batchId"],
        [{"sceneId": item["sceneId"], "candidateId": candidate["candidateId"]}],
    )
    assert result["bound"] == [
        {"sceneId": "scene_1", "assetId": "visual_ai_image_scene_1"}
    ]
    updated = project_service.get_project(project.id).model_dump(mode="python")
    scene = updated["structuredContent"]["episode"]["visualPlan"]["scenes"][0]
    asset = next(value for value in updated["assets"] if value["id"] == scene["primaryAssetId"])
    assert scene["visualAssetIds"] == ["visual_ai_image_scene_1"]
    assert asset["metadata"]["generatedBy"] == "ai_image"
    assert asset["metadata"]["channel"] == "agent"
    assert asset["metadata"]["inputHash"] == item["inputHash"]
    assert (tmp_path / project.id / asset["path"]).is_file()


def test_upload_and_approval_reject_stale_inputs_without_mutation(tmp_path, monkeypatch):
    project = _timed_project(tmp_path, monkeypatch)
    batch = create_batch(project.id, channel="agent")
    item = batch["items"][0]
    image = tmp_path / "generated.png"
    image.write_bytes(_PNG)

    with pytest.raises(ImageGenerationError, match="stale"):
        upload_agent_candidate(
            project.id, batch["batchId"], item["sceneId"], "0" * 64, image
        )

    candidate = upload_agent_candidate(
        project.id, batch["batchId"], item["sceneId"], item["inputHash"], image
    )
    before = project_service.get_project(project.id)
    blocks = [value.model_dump() for value in before.structuredContent.episode.blocks]
    blocks[0]["revision"] = 2
    project_service.update_project(
        project.id,
        {
            "structuredContent": {
                **before.structuredContent.model_dump(),
                "episode": {
                    **before.structuredContent.episode.model_dump(),
                    "blocks": blocks,
                },
            }
        },
    )

    with pytest.raises(ImageGenerationError, match="stale"):
        approve_candidates(
            project.id,
            batch["batchId"],
            [{"sceneId": item["sceneId"], "candidateId": candidate["candidateId"]}],
        )
    assert project_service.get_project(project.id).assets == []
    assert get_batch(project.id, batch["batchId"])["status"] == "stale"


def test_retry_only_resets_failed_items(tmp_path, monkeypatch):
    project = _timed_project(tmp_path, monkeypatch)
    batch = create_batch(project.id, channel="agent")
    first, second = batch["items"]
    image = tmp_path / "generated.png"
    image.write_bytes(_PNG)
    upload_agent_candidate(
        project.id, batch["batchId"], first["sceneId"], first["inputHash"], image
    )
    record_item_failure(project.id, batch["batchId"], second["sceneId"], "provider_error", "boom")

    retried = retry_failed_items(project.id, batch["batchId"])

    by_scene = {item["sceneId"]: item for item in retried["items"]}
    assert by_scene[first["sceneId"]]["status"] == "generated"
    assert len(by_scene[first["sceneId"]]["candidates"]) == 1
    assert by_scene[second["sceneId"]]["status"] == "pending"
    assert by_scene[second["sceneId"]]["error"] == ""
