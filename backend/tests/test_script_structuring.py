import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import create_app
from services import project_service, structure_profile_service
from services.script_structuring_service import ScriptStructuringRequest, ScriptStructuringService


class FakeProvider:
    name = "fake"

    def structure(self, request):
        assert request.source_text == "A natural-language script"
        return {
            "title": "Provider title",
            "sections": [
                {"type": "HOOK", "text": "Open with a precise hook."},
                {"type": "STORY", "text": "Develop the core story."},
            ],
        }


def test_service_normalizes_provider_proposal_into_valid_episode():
    result = ScriptStructuringService(FakeProvider()).propose(
        ScriptStructuringRequest(source_text="A natural-language script", target_duration_seconds=60)
    )
    episode = result["episode"]
    assert episode["title"] == "Provider title"
    assert [block["id"] for block in episode["blocks"]] == ["hook_01", "story_01"]
    assert episode["activeVariantId"] == "publish"
    assert episode["metadata"]["scriptStructuring"]["provider"] == "fake"
    assert "start" not in str(episode).lower()


def test_normalize_api_accepts_profile_snapshot_without_profile_service():
    client = TestClient(create_app())
    response = client.post(
        "/api/script-structuring/normalize",
        json={
            "sourceText": "Natural source",
            "profileSnapshot": {"id": "knowledge-v1", "version": 1, "allowedBlockTypes": ["HOOK", "STORY"]},
            "proposal": {"title": "Draft", "sections": [{"type": "HOOK", "text": "Hook"}, {"type": "STORY", "text": "Story"}]},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["episode"]["metadata"]["scriptStructuring"]["profileSnapshot"]["id"] == "knowledge-v1"
    assert body["episode"]["variants"][0]["id"] == "publish"


def test_normalize_api_rejects_profile_disallowed_block_type():
    client = TestClient(create_app())
    response = client.post(
        "/api/script-structuring/normalize",
        json={
            "sourceText": "Natural source",
            "profileSnapshot": {"allowedBlockTypes": ["HOOK"]},
            "proposal": {"sections": [{"type": "STORY", "text": "Story"}]},
        },
    )
    assert response.status_code == 422
    assert "not allowed" in response.json()["detail"]


def test_normalize_api_honors_block_types_from_project_profile_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(structure_profile_service, "PROFILES_DIR", tmp_path / "config" / "structure_profiles")
    client = TestClient(create_app())
    profile = client.post("/api/structure-profiles", json={
        "name": "Hook-only", "blocks": [{"id": "hook", "type": "HOOK", "label": "Hook"}],
    }).json()
    project = client.post("/api/projects", json={"name": "Snapshot contract"}).json()
    snapshot = client.post(
        f"/api/projects/{project['id']}/structure-profile-snapshot", json={"profileId": profile["id"]},
    ).json()["structureProfileSnapshot"]

    response = client.post("/api/script-structuring/normalize", json={
        "sourceText": "Natural source", "profileSnapshot": snapshot,
        "proposal": {"sections": [{"type": "STORY", "text": "Not allowed"}]},
    })

    assert response.status_code == 422
    assert "not allowed" in response.json()["detail"]


def test_propose_api_does_not_call_an_unconfigured_external_model():
    client = TestClient(create_app())
    response = client.post("/api/script-structuring/propose", json={"sourceText": "Natural source"})
    assert response.status_code == 503
    assert response.json()["detail"] == "script_structuring_provider_not_configured"
