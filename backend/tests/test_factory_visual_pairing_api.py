from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import project_service
from test_agent_factory_two_stage import _paused_factory


def test_item_visuals_exposes_plan_order_timing_and_safe_audio_url(monkeypatch, tmp_path):
    client, batch_id, row, _ = _paused_factory(monkeypatch, tmp_path, key="pairing_detail")
    response = client.get(f"/api/agent-factory/batches/{batch_id}/items/one/visuals")
    assert response.status_code == 200
    payload = response.json()
    assert payload["projectId"] == row["projectId"]
    assert [scene["sceneIndex"] for scene in payload["scenes"]] == [1, 2, 3]
    assert [(scene["start"], scene["end"]) for scene in payload["scenes"]] == [(0.0, 5.0), (5.0, 10.0), (10.0, 15.0)]
    assert all(scene["text"] for scene in payload["scenes"])
    assert payload["audio"]["url"].startswith(f"/api/projects/{row['projectId']}/")
    assert str(tmp_path) not in str(payload)


def test_explicit_shuffled_upload_binding_and_unbind(monkeypatch, tmp_path):
    client, batch_id, _, _ = _paused_factory(monkeypatch, tmp_path, key="pairing_upload")
    details = client.get(f"/api/agent-factory/batches/{batch_id}/items/one/visuals").json()
    scenes = details["scenes"]
    for scene in scenes:
        response = client.post(f"/api/agent-factory/batches/{batch_id}/items/one/visuals/unbind", json={"sceneId": scene["sceneId"], "deleteProjectAsset": True})
        assert response.status_code == 200
    # Deliberately upload in ending/opening/middle order: explicit sceneId is authoritative.
    uploads = [(scenes[2], "ending.png", b"ending"), (scenes[0], "opening.png", b"opening"), (scenes[1], "middle.mp4", b"middle")]
    for scene, name, body in uploads:
        response = client.post(f"/api/agent-factory/batches/{batch_id}/items/one/visuals/upload", data={"sceneId": scene["sceneId"], "replace": "false"}, files={"file": (name, body, "video/mp4" if name.endswith("mp4") else "image/png")})
        assert response.status_code == 200, response.text
    final = client.get(f"/api/agent-factory/batches/{batch_id}/items/one/visuals").json()
    assert final["coverage"]["complete"] is True
    assert [scene["boundAsset"]["name"] for scene in final["scenes"]] == ["scene_story_01_001.png", "scene_mechanism_01_001.mp4", "scene_method_01_001.png"]
    unbound = client.post(f"/api/agent-factory/batches/{batch_id}/items/one/visuals/unbind", json={"sceneId": scenes[1]["sceneId"], "deleteProjectAsset": True})
    assert unbound.status_code == 200 and unbound.json()["coverage"]["complete"] is False
    assert client.post(f"/api/agent-factory/batches/{batch_id}/items/one/resume", json={}).status_code == 409
    project = project_service.get_project(final["projectId"])
    assert len(project.assets) == 2
