import json
from vforge import client, mcp_server

def test_factory_mcp_delegates_to_client(monkeypatch):
    monkeypatch.setattr(client,"factory_pending_visuals",lambda batch:{"batchId":batch,"items":[]})
    monkeypatch.setattr(client,"factory_continue",lambda batch:{"batchId":batch,"status":"awaiting_visual_assets"})
    assert json.loads(mcp_server.get_pending_visual_scenes("b"))["batchId"]=="b"
    assert json.loads(mcp_server.continue_agent_video_factory("b"))["status"]=="awaiting_visual_assets"
