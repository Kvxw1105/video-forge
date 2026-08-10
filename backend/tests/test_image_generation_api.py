from __future__ import annotations

import base64
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import create_app
from models.image_generation import ImageProviderSettings
from services import image_generation_service, project_service
from shared.visual_scene import visual_source_hash


_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP4z8DwHwAF"
    "AAH/iZk9HQAAAABJRU5ErkJggg=="
)


def _project(tmp_path, monkeypatch):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    project = project_service.create_project("API image scenes")
    structured = {
        "schemaVersion": 1,
        "episode": {
            "episodeId": "episode_api",
            "blocks": [{"id": "story", "type": "STORY", "text": "A lighthouse in fog."}],
            "variants": [{"id": "publish", "name": "Publish", "blockIds": ["story"]}],
            "activeVariantId": "publish",
            "bindings": [{"blockId": "story", "duration": 2.0, "subtitleIds": ["s1"]}],
        },
    }
    project = project_service.update_project(
        project.id,
        {
            "subtitles": [{"id": "s1", "text": "A lighthouse in fog.", "start": 0, "end": 2}],
            "structuredContent": structured,
        },
    )
    plan = {
        "schemaVersion": 1,
        "planId": "plan_api",
        "sourceHash": visual_source_hash(project.model_dump()),
        "scenes": [
            {
                "id": "scene_api",
                "blockId": "story",
                "subtitleIds": ["s1"],
                "prompt": "cinematic lighthouse emerging from fog",
            }
        ],
        "settings": {},
    }
    return project_service.update_project(
        project.id,
        {
            "structuredContent": {
                **project.structuredContent.model_dump(),
                "episode": {**project.structuredContent.episode.model_dump(), "visualPlan": plan},
            }
        },
    )


class _ImageResponse:
    status_code = 200
    headers = {"content-type": "application/json"}
    text = ""

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "data": [
                {
                    "b64_json": base64.b64encode(_PNG).decode("ascii"),
                    "revised_prompt": "cinematic lighthouse in restrained colors",
                }
            ]
        }


class _PrivateUrlResponse(_ImageResponse):
    def json(self):
        return {"data": [{"url": "http://127.0.0.1/private.png"}]}


def test_provider_settings_mask_and_preserve_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(image_generation_service, "_SETTINGS_FILE", tmp_path / "image.json")
    app = create_app()
    client = TestClient(app)

    saved = client.put(
        "/api/settings/ai-image",
        json={
            "enabled": True,
            "baseUrl": "https://images.example/v1",
            "apiKey": "image-secret",
            "model": "image-model",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["apiKey"] == ""
    assert saved.json()["apiKeyConfigured"] is True

    updated = client.put(
        "/api/settings/ai-image",
        json={"apiKey": "", "apiKeyConfigured": True, "maxConcurrency": 2},
    )
    assert updated.status_code == 200
    assert image_generation_service.load_image_provider_settings().apiKey == "image-secret"
    assert image_generation_service.load_image_provider_settings().maxConcurrency == 2
    assert "image-secret" not in client.get("/api/settings/ai-image").text


def test_builtin_provider_generates_candidate_and_agent_http_uploads(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(image_generation_service, "_SETTINGS_FILE", tmp_path / "image.json")
    image_generation_service.save_image_provider_settings(
        ImageProviderSettings(
            enabled=True,
            baseUrl="https://images.example/v1",
            apiKey="image-secret",
            model="image-model",
            maxConcurrency=2,
        )
    )
    monkeypatch.setattr(image_generation_service.httpx, "post", lambda *args, **kwargs: _ImageResponse())

    built_in = image_generation_service.create_batch(
        project.id, channel="builtin", provider_id="openai-compatible", model="image-model"
    )
    generated = image_generation_service.run_builtin_batch(project.id, built_in["batchId"])
    assert generated["status"] == "awaiting_approval"
    assert generated["items"][0]["candidates"][0]["revisedPrompt"].startswith("cinematic")

    app = create_app()
    client = TestClient(app)
    created = client.post(
        f"/api/projects/{project.id}/image-generation/batches",
        json={"channel": "agent", "providerId": "codex-imagegen"},
    )
    assert created.status_code == 200
    batch = created.json()
    pending = client.get(
        f"/api/projects/{project.id}/image-generation/batches/{batch['batchId']}/pending"
    )
    assert pending.status_code == 200
    item = pending.json()["items"][0]
    uploaded = client.post(
        f"/api/projects/{project.id}/image-generation/batches/{batch['batchId']}/upload",
        data={"sceneId": item["sceneId"], "inputHash": item["inputHash"]},
        files={"file": ("scene.png", _PNG, "image/png")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["candidateId"].startswith("candidate_scene_api_")

    stale = client.post(
        f"/api/projects/{project.id}/image-generation/batches/{batch['batchId']}/upload",
        data={"sceneId": item["sceneId"], "inputHash": "0" * 64},
        files={"file": ("scene.png", _PNG, "image/png")},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "input_stale"


def test_builtin_provider_blocks_private_url_and_retries_failed_item(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(image_generation_service, "_SETTINGS_FILE", tmp_path / "image.json")
    image_generation_service.save_image_provider_settings(
        ImageProviderSettings(
            enabled=True,
            baseUrl="https://images.example/v1",
            apiKey="image-secret",
            model="image-model",
        )
    )
    monkeypatch.setattr(
        image_generation_service.httpx,
        "post",
        lambda *args, **kwargs: _PrivateUrlResponse(),
    )
    batch = image_generation_service.create_batch(project.id, channel="builtin")

    failed = image_generation_service.run_builtin_batch(project.id, batch["batchId"])
    assert failed["status"] == "failed"
    assert failed["items"][0]["errorCode"] == "provider_image_url_blocked"

    retried = image_generation_service.retry_failed_items(project.id, batch["batchId"])
    assert retried["items"][0]["status"] == "pending"
    monkeypatch.setattr(
        image_generation_service.httpx,
        "post",
        lambda *args, **kwargs: _ImageResponse(),
    )
    succeeded = image_generation_service.run_builtin_batch(project.id, batch["batchId"])
    assert succeeded["status"] == "awaiting_approval"
    assert succeeded["items"][0]["attempts"] == 2
