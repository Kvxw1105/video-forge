from pathlib import Path

from fastapi.testclient import TestClient

from main import create_app
from routers import visual_assets
from services import project_service


def _project_with_visual_plan(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(visual_assets, "PROJECTS_DIR", tmp_path)
    project = project_service.create_project("stickman")
    project_service.update_project(project.id, {
        "subtitles": [
            {"id": "s1", "text": "越害怕失去的人，越容易提前控制关系。", "start": 0, "end": 2, "style": {}, "metadata": {}},
            {"id": "s2", "text": "他背着整个家族的期待，却没有人问过他累不累。", "start": 2, "end": 4, "style": {}, "metadata": {}},
        ],
        "structuredContent": {
            "schemaVersion": 1,
            "episode": {
                "episodeId": "ep",
                "blocks": [{"id": "story", "type": "STORY", "text": "story"}],
                "variants": [{"id": "publish", "name": "Publish", "blockIds": ["story"]}],
                "activeVariantId": "publish",
                "bindings": [{"blockId": "story", "duration": 4, "subtitleIds": ["s1", "s2"]}],
            },
        },
    })
    client = TestClient(create_app())
    proposed = client.post(f"/api/projects/{project.id}/visual-plan/propose", json={"mode": "fixed_units", "unitsPerScene": 1}).json()
    plan = {"planId": "plan_stickman", "sourceHash": proposed["sourceHash"], "scenes": proposed["scenes"], "settings": {"mode": "fixed_units", "unitsPerScene": 1}}
    assert client.put(f"/api/projects/{project.id}/visual-plan", json={"plan": plan}).status_code == 200
    return client, project.id


def test_http_render_registers_png_and_binds_visual_scenes(monkeypatch, tmp_path):
    client, project_id = _project_with_visual_plan(monkeypatch, tmp_path)
    response = client.post(f"/api/projects/{project_id}/visual-assets/stickman/render", json={"sourceMode": "visual_plan", "exportPng": True, "bindToProject": True})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert len(payload["bindings"]) == 2
    project = client.get(f"/api/projects/{project_id}").json()
    assert len(project["assets"]) == 2
    scenes = project["structuredContent"]["episode"]["visualPlan"]["scenes"]
    assert all(scene["primaryAssetId"].startswith("visual_stickman_") for scene in scenes)
    for asset in project["assets"]:
        assert (tmp_path / project_id / asset["path"]).exists()
    run = client.get(f"/api/projects/{project_id}/visual-assets/stickman/runs/{payload['runId']}")
    assert run.status_code == 200
    assert run.json()["manifest"]["items"][0]["pngPath"]


def test_http_regenerate_one_scene_does_not_unbind_other_scene(monkeypatch, tmp_path):
    client, project_id = _project_with_visual_plan(monkeypatch, tmp_path)
    rendered = client.post(f"/api/projects/{project_id}/visual-assets/stickman/render", json={"sourceMode": "visual_plan", "exportPng": True, "bindToProject": True}).json()
    project = client.get(f"/api/projects/{project_id}").json()
    original = project["structuredContent"]["episode"]["visualPlan"]["scenes"][1]["primaryAssetId"]
    scene_id = project["structuredContent"]["episode"]["visualPlan"]["scenes"][0]["id"]
    regenerated = client.post(f"/api/projects/{project_id}/visual-assets/stickman/scenes/{scene_id}/regenerate", json={"exportPng": True})
    assert regenerated.status_code == 200, regenerated.text
    after = client.get(f"/api/projects/{project_id}").json()
    assert after["structuredContent"]["episode"]["visualPlan"]["scenes"][1]["primaryAssetId"] == original
