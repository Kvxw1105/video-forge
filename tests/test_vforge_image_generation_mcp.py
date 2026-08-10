import json

from vforge import client, mcp_server


def test_mcp_image_generation_tools_delegate_to_http_client(monkeypatch):
    monkeypatch.setattr(client, "create_image_generation_batch", lambda pid, data: {"batchId": "b1"})
    monkeypatch.setattr(client, "get_pending_image_generation_requests", lambda pid, batch: {"items": [{"sceneId": "s1"}]})
    monkeypatch.setattr(client, "upload_image_generation_candidate", lambda pid, batch, scene, input_hash, file_path: {"candidateId": "c1"})
    monkeypatch.setattr(client, "approve_image_generation_candidates", lambda pid, batch, selections: {"bound": selections})

    assert json.loads(mcp_server.create_scene_image_batch("p1", {"channel": "agent"}))["batchId"] == "b1"
    assert json.loads(mcp_server.get_pending_scene_image_requests("p1", "b1"))["items"][0]["sceneId"] == "s1"
    assert json.loads(mcp_server.upload_scene_image_candidate("p1", "b1", "s1", "a" * 64, "D:/scene.png"))["candidateId"] == "c1"
    assert json.loads(mcp_server.approve_scene_image_candidates("p1", "b1", [{"sceneId": "s1", "candidateId": "c1"}]))["bound"][0]["candidateId"] == "c1"
