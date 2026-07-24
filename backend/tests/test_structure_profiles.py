import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import create_app
from services import project_service, structure_profile_service


def _client(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(structure_profile_service, "PROFILES_DIR", tmp_path / "config" / "structure_profiles")
    return TestClient(create_app())


def _custom_profile(name="我的结构"):
    return {
        "name": name,
        "description": "用于测试的自定义规则",
        "blocks": [
            {
                "id": "hook",
                "type": "HOOK",
                "label": "开头",
                "targetChars": 80,
                "visualPolicy": {"style": "black_screen_text", "scenePolicy": "single_clip"},
            },
            {
                "id": "story",
                "type": "STORY",
                "label": "主体",
                "required": False,
                "visualPolicy": {"style": "cinematic_images", "scenePolicy": "split_by_semantic_cluster"},
            },
        ],
    }


def test_lists_builtin_profiles_with_semantic_and_visual_rules(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    response = client.get("/api/structure-profiles")

    assert response.status_code == 200
    profiles = response.json()
    assert {item["id"] for item in profiles} == {
        "knowledge_explainer", "story_narrative", "product_recommendation"
    }
    knowledge = next(item for item in profiles if item["id"] == "knowledge_explainer")
    assert knowledge["builtin"] is True
    assert knowledge["blocks"][0]["visualPolicy"]["scenePolicy"] == "single_clip"


def test_user_profile_crud_versions_and_rejects_builtin_write(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    created = client.post("/api/structure-profiles", json=_custom_profile())
    assert created.status_code == 201
    body = created.json()
    profile_id = body["id"]
    assert profile_id.startswith("profile_")
    assert body["version"] == 1
    assert body["builtin"] is False

    updated = client.put(f"/api/structure-profiles/{profile_id}", json={**_custom_profile("重命名"), "id": profile_id})
    assert updated.status_code == 200
    assert updated.json()["name"] == "重命名"
    assert updated.json()["version"] == 2

    assert client.put("/api/structure-profiles/knowledge_explainer", json=_custom_profile()).status_code == 403
    assert client.delete("/api/structure-profiles/knowledge_explainer").status_code == 403
    assert client.delete(f"/api/structure-profiles/{profile_id}").status_code == 200
    assert client.get(f"/api/structure-profiles/{profile_id}").status_code == 404


def test_profile_validation_rejects_unknown_block_type_and_duplicate_rule_ids(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    unknown = _custom_profile()
    unknown["blocks"][0]["type"] = "CUSTOM"
    assert client.post("/api/structure-profiles", json=unknown).status_code == 422

    duplicate = _custom_profile()
    duplicate["blocks"][1]["id"] = "hook"
    assert client.post("/api/structure-profiles", json=duplicate).status_code == 422


def test_project_snapshot_is_immutable_after_profile_changes(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    profile = client.post("/api/structure-profiles", json=_custom_profile()).json()
    project = client.post("/api/projects", json={"name": "Snapshot project"}).json()

    attached = client.post(
        f"/api/projects/{project['id']}/structure-profile-snapshot",
        json={"profileId": profile["id"]},
    )
    assert attached.status_code == 200
    snapshot = attached.json()["structureProfileSnapshot"]
    assert snapshot["profileId"] == profile["id"]
    assert snapshot["profileVersion"] == 1
    assert snapshot["profile"]["name"] == "我的结构"

    changed = client.put(
        f"/api/structure-profiles/{profile['id']}",
        json={**_custom_profile("更新后的结构"), "id": profile["id"]},
    )
    assert changed.status_code == 200
    assert changed.json()["version"] == 2

    stored = client.get(f"/api/projects/{project['id']}/structure-profile-snapshot")
    assert stored.status_code == 200
    assert stored.json()["structureProfileSnapshot"]["profileVersion"] == 1
    assert stored.json()["structureProfileSnapshot"]["profile"]["name"] == "我的结构"
