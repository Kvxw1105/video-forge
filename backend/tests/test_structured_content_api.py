import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import create_app
from services import project_service


def _project_payload():
    return {
        "name": "structured",
        "structuredContent": {
            "schemaVersion": 1,
            "episode": {
                "episodeId": "episode_api",
                "title": "API episode",
                "blocks": [
                    {"id": "a", "type": "HOOK", "text": "A"},
                    {"id": "b", "type": "STORY", "text": "B"},
                    {"id": "c", "type": "SHORT_OUTRO", "text": "C", "enabled": False},
                ],
                "variants": [
                    {"id": "publish", "name": "Publish", "blockIds": ["a", "b", "c"]},
                    {"id": "master", "name": "Master", "blockIds": ["b"]},
                    {"id": "chapter", "name": "Chapter", "blockIds": ["a", "b"]},
                ],
                "activeVariantId": "publish",
            },
        },
    }


def _client(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    return TestClient(create_app())


def test_compile_api_returns_publish_master_and_chapter(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    created = client.post("/api/projects", json=_project_payload()).json()
    project_id = created["id"]
    # The create endpoint intentionally accepts only its existing create fields;
    # attach structuredContent through the existing update contract.
    response = client.put(f"/api/projects/{project_id}", json={"structuredContent": _project_payload()["structuredContent"]})
    assert response.status_code == 200
    for variant, expected in [("publish", ["a", "b"]), ("master", ["b"]), ("chapter", ["a", "b"])]:
        result = client.get(f"/api/projects/{project_id}/structured/variants/{variant}/compile")
        assert result.status_code == 200
        assert result.json()["blockIds"] == expected


def test_compile_api_errors_and_does_not_write(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    created = client.post("/api/projects", json={"name": "legacy"}).json()
    project_id = created["id"]
    project_file = tmp_path / project_id / "project.json"
    before = project_file.read_text(encoding="utf-8")
    assert client.get(f"/api/projects/{project_id}/structured/variants/publish/compile").status_code == 409
    assert client.get(f"/api/projects/{project_id}/structured/variants/missing/compile").status_code == 409
    assert client.get("/api/projects/missing/structured/variants/publish/compile").status_code == 404
    assert project_file.read_text(encoding="utf-8") == before


def test_compile_api_missing_variant_is_404(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    created = client.post("/api/projects", json=_project_payload()).json()
    project_id = created["id"]
    client.put(f"/api/projects/{project_id}", json={"structuredContent": _project_payload()["structuredContent"]})
    response = client.get(f"/api/projects/{project_id}/structured/variants/missing/compile")
    assert response.status_code == 404


def test_invalid_structured_update_returns_422(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    created = client.post("/api/projects", json={"name": "legacy"}).json()
    invalid = {"structuredContent": {"schemaVersion": 2, "episode": {}}}
    response = client.put(f"/api/projects/{created['id']}", json=invalid)
    assert response.status_code == 422
