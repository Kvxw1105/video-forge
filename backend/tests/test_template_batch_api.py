import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import create_app
from services import project_service, template_batch_service as batches


def test_batch_plan_api_is_read_only(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(batches, "PROJECTS_DIR", tmp_path)
    client = TestClient(create_app())
    payload = {"schemaVersion": 1, "name": "plan", "idempotencyKey": "plan_001", "templateId": "tpl_single_voiceover", "defaults": {"voiceover": {"enabled": False, "engine": "none"}, "outputs": {"preview": False, "jianyingDirect": False, "jianyingZip": False}}, "items": [{"itemId": "one", "name": "One", "script": "text", "assets": {"images": [], "videos": [], "bgm": None}}]}
    response = client.post("/api/batches/template-production/plan", json=payload)
    assert response.status_code == 200 and response.json()["valid"] is True
    assert not (tmp_path / ".batches").exists()
