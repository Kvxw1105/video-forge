import json

from vforge import client, mcp_server


def test_video_director_mcp_tools_delegate_to_client(monkeypatch):
    monkeypatch.setattr(client, "inspect_video_project", lambda pid: {"projectId": pid})
    monkeypatch.setattr(client, "create_video_factory_job", lambda spec: {"batchId": spec["batchId"]})
    monkeypatch.setattr(client, "prepare_structured_script", lambda spec: {"mode": "parsed_text", "proposal": spec})
    monkeypatch.setattr(client, "review_visual_scene_plan", lambda pid, settings=None, plan=None, expected_updated_at=None, persist=False: {"projectId": pid, "mode": "current"})
    monkeypatch.setattr(client, "prepare_visual_generation_pack", lambda pid: {"projectId": pid, "pack": []})
    monkeypatch.setattr(client, "inspect_pending_visuals", lambda batch_id: {"batchId": batch_id, "items": []})
    monkeypatch.setattr(client, "bind_scene_assets", lambda batch_id, item_id, data: {"batchId": batch_id, "itemId": item_id, "data": data})
    monkeypatch.setattr(client, "validate_video_assets", lambda batch_id, item_id: {"batchId": batch_id, "itemId": item_id, "ok": True})
    monkeypatch.setattr(client, "validate_video_readiness", lambda pid, batch_id=None, item_id=None: {"projectId": pid, "ready": True})
    monkeypatch.setattr(client, "inspect_video_readiness", lambda pid, batch_id=None, item_id=None: {"projectId": pid, "ready": True, "alias": True})
    monkeypatch.setattr(client, "build_video_preview", lambda pid: {"projectId": pid, "previewPath": "preview.mp4"})
    monkeypatch.setattr(client, "audit_video_preview", lambda pid: {"projectId": pid, "result": "passed"})
    monkeypatch.setattr(client, "export_editable_draft", lambda pid: {"projectId": pid, "policy": "create_new"})
    monkeypatch.setattr(client, "recover_video_job", lambda batch_id, item_id=None: {"batchId": batch_id, "itemId": item_id})
    monkeypatch.setattr(client, "get_video_job_status", lambda batch_id: {"batchId": batch_id, "status": "running"})

    assert json.loads(mcp_server.inspect_video_project("p1"))["projectId"] == "p1"
    assert json.loads(mcp_server.create_video_factory_job({"batchId": "b1"}))["batchId"] == "b1"
    assert json.loads(mcp_server.prepare_structured_script({"text": "hello"}))["mode"] == "parsed_text"
    assert json.loads(mcp_server.review_visual_scene_plan("p1"))["mode"] == "current"
    assert json.loads(mcp_server.prepare_visual_generation_pack("p1"))["pack"] == []
    assert json.loads(mcp_server.inspect_pending_visuals("b1"))["items"] == []
    assert json.loads(mcp_server.bind_scene_assets("b1", "i1", {"folder": "x"}))["data"]["folder"] == "x"
    assert json.loads(mcp_server.validate_video_assets("b1", "i1"))["ok"] is True
    assert json.loads(mcp_server.validate_video_readiness("p1"))["ready"] is True
    assert json.loads(mcp_server.inspect_video_readiness("p1"))["alias"] is True
    assert json.loads(mcp_server.build_video_preview("p1"))["previewPath"] == "preview.mp4"
    assert json.loads(mcp_server.audit_video_preview("p1"))["result"] == "passed"
    assert json.loads(mcp_server.export_editable_draft("p1"))["policy"] == "create_new"
    assert json.loads(mcp_server.recover_video_job("b1", "i1"))["itemId"] == "i1"
    assert json.loads(mcp_server.get_video_job_status("b1"))["status"] == "running"
