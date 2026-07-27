"""HTTP verification of the user-visible Private Skill -> Pack -> Director path."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from agent.lab_runner.run_store import RunStore
from agent_runtime.director_service import DirectorService
from agent_runtime.director_store import DirectorStore
from agent_runtime.director_studio import DirectorStudioRegistry
from agent_runtime.pi_transport import FakePiTransport
from routers import director, director_studio
from services import project_service


def main() -> int:
    from main import create_app

    old_registry = director_studio.registry
    old_studio = director.studio
    old_service = director.service
    old_projects_dir = project_service.PROJECTS_DIR
    with tempfile.TemporaryDirectory(prefix="videoforge-director-studio-api-") as temp:
        root = Path(temp)
        registry = DirectorStudioRegistry(root=root / "studio", recipes_root=ROOT / "agent" / "recipes")
        project_service.PROJECTS_DIR = root / "projects"
        director_studio.registry = registry
        director.studio = registry
        director.service = DirectorService(store=DirectorStore(RunStore(root / "runs")), transport=FakePiTransport())
        try:
            client = TestClient(create_app())
            initial = client.get("/api/director-studio/skills")
            assert initial.status_code == 200 and any(row["skillId"] == "subtitle_scene_director" for row in initial.json()["skills"]), initial.text

            draft_response = client.post("/api/director-studio/skills/import-gpt", json={"text": "纪录片知识视频。字幕一句一个画面，暖棕与金色，替换素材必须审批。"})
            assert draft_response.status_code == 200, draft_response.text
            draft = draft_response.json()["skill"]
            assert client.post(f"/api/director-studio/skills/{draft['skillId']}/validate").json()["ok"] is True
            published = client.post(f"/api/director-studio/skills/{draft['skillId']}/publish")
            assert published.status_code == 200 and published.json()["skill"]["status"] == "published", published.text
            trial = client.post(f"/api/director-studio/skills/{draft['skillId']}/trial")
            assert trial.status_code == 200 and trial.json()["scenePlan"]["scenes"], trial.text

            pack_response = client.post("/api/director-studio/packs", json={
                "name": "API 验收纪录片包",
                "recipeId": "structured-knowledge-video",
                "skillPins": [{"skillId": draft["skillId"], "version": 1}],
                "style": {"name": "纪录片", "palette": "暖棕金色", "mood": "克制"},
                "capabilityIds": ["review_visual_scene_plan", "bind_scene_assets"],
            })
            assert pack_response.status_code == 200, pack_response.text
            pack = pack_response.json()["pack"]
            exported = client.get(f"/api/director-studio/packs/{pack['packId']}/export")
            assert exported.status_code == 200 and exported.json()["pack"]["skillPins"][0]["version"] == 1, exported.text

            second_pack_response = client.post("/api/director-studio/packs", json={
                "name": "API 验收拼贴包",
                "recipeId": "structured-knowledge-video",
                "skillPins": [{"skillId": "subtitle_scene_director", "version": 1}],
                "style": {"name": "报纸拼贴", "palette": "黑白红", "mood": "锐利"},
                "capabilityIds": ["review_visual_scene_plan", "bind_scene_assets"],
            })
            assert second_pack_response.status_code == 200, second_pack_response.text
            second_pack = second_pack_response.json()["pack"]

            # This is a durable synthetic VideoForge project, not only an
            # in-memory SRT payload.  Both packs must make a visible plan diff.
            project = project_service.create_project("Skill Pack synthetic project")
            project_service.update_project(project.id, {"script": "先看清问题。再给出解决路径。", "subtitles": [
                {"id": "synthetic_scene_a", "start": 0, "end": 2, "text": "先看清问题。", "style": {}},
                {"id": "synthetic_scene_b", "start": 2, "end": 5, "text": "再给出解决路径。", "style": {}},
            ]})
            first_project_run = client.post("/api/director/runs", json={"task": "Plan the synthetic project.", "projectId": project.id, "packId": pack["packId"]})
            second_project_run = client.post("/api/director/runs", json={"task": "Plan the synthetic project.", "projectId": project.id, "packId": second_pack["packId"]})
            assert first_project_run.status_code == 200 and second_project_run.status_code == 200
            first_plan = first_project_run.json()["scenePlan"]
            second_plan = second_project_run.json()["scenePlan"]
            assert first_plan["scenes"][0]["sceneId"] == "synthetic_scene_a"
            assert first_plan["styleSignature"] != second_plan["styleSignature"]

            intake = {
                "source": {"type": "srt_upload", "filename": "acceptance.srt"},
                "subtitleTimeline": [
                    {"start": 0, "end": 2, "text": "先看清问题。"},
                    {"start": 2, "end": 5, "text": "再给出解决路径。"},
                ],
            }
            run_response = client.post("/api/director/runs", json={"task": "Use the private Pack.", "packId": pack["packId"], "intake": intake})
            assert run_response.status_code == 200, run_response.text
            run = run_response.json()
            assert run["directorPack"]["packId"] == pack["packId"], run
            assert run["scenePlan"]["scenes"][0]["visualStyle"].startswith("纪录片"), run
            assert any(event["type"] == "scene_plan.proposed" for event in client.get(f"/api/director/runs/{run['runId']}/events").json()["events"])
            assert client.delete(f"/api/director-studio/packs/{pack['packId']}").status_code == 200
            print({"skill": draft["skillId"], "pack": pack["packId"], "run": run["runId"], "scenes": len(run["scenePlan"]["scenes"])})
        finally:
            director_studio.registry = old_registry
            director.studio = old_studio
            director.service = old_service
            project_service.PROJECTS_DIR = old_projects_dir
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
