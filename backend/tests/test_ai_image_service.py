from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_runtime.ai_image_settings import AIImageProviderSettings
from routers import ai_image
from services import ai_image_service, project_service


_PNG = base64.b64encode(
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0dIDAT\x08\xd7c\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
).decode()


class _Response:
    status_code = 200
    text = ""
    def raise_for_status(self): pass
    def json(self): return {"data": [{"b64_json": _PNG, "revised_prompt": "resolved"}]}


def test_ai_image_batch_generates_candidates_and_binds_scene(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(ai_image_service, "_project_dir", lambda project_id: tmp_path / project_id)
    monkeypatch.setattr(ai_image_service, "load_ai_image_provider", lambda: AIImageProviderSettings(enabled=True, baseUrl="https://gateway.example/v1", apiKey="key", model="image-model", maxConcurrency=2))
    monkeypatch.setattr(ai_image_service.httpx, "post", lambda *args, **kwargs: _Response())
    project = project_service.create_project("AI image batch")
    project_service.update_project(project.id, {
        "subtitles": [{"id": "s1", "text": "first", "start": 0, "end": 1, "style": {}, "metadata": {}}, {"id": "s2", "text": "second", "start": 1, "end": 2, "style": {}, "metadata": {}}],
        "structuredContent": {"schemaVersion": 1, "episode": {"episodeId": "ep", "blocks": [{"id": "b1", "type": "STORY", "text": "first"}, {"id": "b2", "type": "STORY", "text": "second"}], "variants": [{"id": "v", "name": "V", "blockIds": ["b1", "b2"]}], "activeVariantId": "v", "bindings": [], "visualPlan": {"schemaVersion": 1, "planId": "plan", "sourceHash": "a" * 64, "scenes": [{"id": "scene_1", "blockId": "b1", "subtitleIds": ["s1"], "requestedMediaType": "image", "metadata": {}}, {"id": "scene_2", "blockId": "b2", "subtitleIds": ["s2"], "requestedMediaType": "image", "metadata": {}}], "settings": {}}}},
    })
    batch = ai_image_service.create_batch(project.id, [{"sceneId": "scene_1", "prompt": "one"}, {"sceneId": "scene_2", "prompt": "two"}], model="image-model", size="1024x1024", candidate_count=1)
    complete = ai_image_service.run_batch(project.id, batch["batchId"], lambda *_: None)
    assert complete["status"] == "succeeded"
    assert all(item["candidates"] for item in complete["items"])
    result = ai_image_service.approve_candidates(project.id, batch["batchId"], [{"sceneId": item["sceneId"], "candidateId": item["candidates"][0]["id"]} for item in complete["items"]])
    assert len(result["bound"]) == 2
    final = project_service.get_project(project.id).model_dump(mode="python")
    scenes = final["structuredContent"]["episode"]["visualPlan"]["scenes"]
    assert all(scene["primaryAssetId"].startswith("visual_ai_image_") for scene in scenes)
    assert len([asset for asset in final["assets"] if asset["metadata"].get("generatedBy") == "ai_image"]) == 2
