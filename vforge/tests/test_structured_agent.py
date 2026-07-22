import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vforge import client
from vforge import mcp_server


def project():
    return {"id": "p", "updated_at": "v1", "composition": {"schemaVersion": 1, "compositionId": "c", "title": "C", "items": [{"id": "a", "enabled": True}, {"id": "b", "enabled": True}]}, "structuredContent": {"schemaVersion": 1, "episode": {"blocks": [{"id": "x", "enabled": True}, {"id": "y", "enabled": True}], "variants": [{"id": "publish", "blockIds": ["x", "y"]}]}}}


def test_move_item_uses_updated_at_and_conflict_does_not_write(monkeypatch):
    current = project(); writes = []
    monkeypatch.setattr(client, "get_project", lambda *args, **kwargs: copy.deepcopy(current))
    monkeypatch.setattr(client, "update_project", lambda *args, **kwargs: writes.append(args) or {"updated_at": "v2"})
    conflict = client.move_composition_item("p", "b", "up", expected_updated_at="stale")
    assert conflict["status"] == "conflict"
    assert writes == []
    result = client.move_composition_item("p", "b", "up", expected_updated_at="v1")
    assert len(writes) == 1
    assert result["updated_at"] == "v2"
    assert writes[0][1]["composition"]["items"][0]["id"] == "b"


def test_block_toggle_does_not_touch_text_or_binding(monkeypatch):
    current = project(); current["structuredContent"]["episode"]["blocks"][0]["text"] = "keep"
    writes = []
    monkeypatch.setattr(client, "get_project", lambda *args, **kwargs: copy.deepcopy(current))
    monkeypatch.setattr(client, "update_project", lambda *args, **kwargs: writes.append(args) or args[1])
    client.set_structured_block_enabled("p", "x", False, expected_updated_at="v1")
    data = writes[0][1]["structuredContent"]
    assert data["episode"]["blocks"][0]["enabled"] is False
    assert data["episode"]["blocks"][0]["text"] == "keep"


def test_variant_order_rejects_unknown_duplicate_and_accepts_subset(monkeypatch):
    current = project(); writes = []
    monkeypatch.setattr(client, "get_project", lambda *args, **kwargs: copy.deepcopy(current))
    monkeypatch.setattr(client, "update_project", lambda *args, **kwargs: writes.append(args) or args[1])
    try:
        client.set_variant_block_order("p", "publish", ["x", "x"], expected_updated_at="v1")
    except client.VForgeError as error:
        assert error.status == 422
    client.set_variant_block_order("p", "publish", ["y"], expected_updated_at="v1")
    assert writes[0][1]["structuredContent"]["episode"]["variants"][0]["blockIds"] == ["y"]


def test_mcp_tools_are_registered_and_delegate_to_http_client(monkeypatch):
    assert {"list_structured_projects", "get_composition", "set_structured_block_enabled", "compile_composition", "export_composition_to_jianying"}.issubset(mcp_server.mcp._tool_manager._tools)
    monkeypatch.setattr(mcp_server.client, "list_structured_projects", lambda: [{"projectId": "p"}])
    result = mcp_server.list_structured_projects()
    assert '"projectId": "p"' in result
