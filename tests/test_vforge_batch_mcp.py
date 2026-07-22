import json

from vforge import client, mcp_server


def test_mcp_batch_tools_delegate_to_client(monkeypatch):
    monkeypatch.setattr(client, "plan_template_batch", lambda spec: {"valid": True, "specHash": "h"})
    monkeypatch.setattr(client, "start_template_batch", lambda spec: {"batchId": "batch_1", "status": "queued"})
    assert json.loads(mcp_server.plan_template_batch({"schemaVersion": 1}))["valid"] is True
    assert json.loads(mcp_server.start_template_batch({"schemaVersion": 1}))["batchId"] == "batch_1"
