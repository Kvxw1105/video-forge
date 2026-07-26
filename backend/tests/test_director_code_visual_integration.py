from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.lab_runner.run_store import RunStore
from agent_runtime.director_service import DirectorService
from agent_runtime.director_store import DirectorStore
from agent_runtime.pi_transport import FakePiTransport
from services import project_service
from routers import visual_assets


def test_approved_director_run_renders_code_visual_overlay(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(visual_assets, "PROJECTS_DIR", tmp_path)
    project = project_service.create_project("Director code visual integration")
    project_service.update_project(project.id, {
        "canvas": {"ratio": "9:16", "width": 270, "height": 480, "fps": 12, "background": {"type": "color", "value": "#000000"}},
        "subtitles": [{"id": "s1", "text": "evidence", "start": 0.0, "end": 1.0, "style": {}, "metadata": {}}],
        "structuredContent": {"schemaVersion": 1, "episode": {
            "episodeId": "ep", "blocks": [{"id": "b1", "type": "STORY", "text": "evidence"}],
            "variants": [{"id": "publish", "name": "Publish", "blockIds": ["b1"]}], "activeVariantId": "publish",
            "bindings": [{"blockId": "b1", "duration": 1.0, "subtitleIds": ["s1"]}],
            "visualPlan": {"schemaVersion": 1, "planId": "plan_director", "sourceHash": "a" * 64, "scenes": [{"id": "scene_director", "blockId": "b1", "subtitleIds": ["s1"], "requestedMediaType": "video", "metadata": {"semantic": {"visualIntent": "evidence", "metadata": {"visualFamily": "evidence"}}}}], "settings": {"mode": "fixed_units", "unitsPerScene": 1}},
        }},
    })
    intake = {"source": {"type": "project", "projectId": project.id}, "structuredContent": project_service.get_project(project.id).model_dump(mode="python")["structuredContent"]}
    service = DirectorService(store=DirectorStore(RunStore(tmp_path / "runs")), transport=FakePiTransport())
    run = service.create_run({"recipeId": "structured-knowledge-video", "task": "render", "intake": intake})
    approved = service.decide_approval(run["runId"], {"approvalId": run["currentApprovalId"], "decision": "approve"})
    assert approved["status"] == "succeeded"
    assert any(call.get("toolName") == "code_visual.render_overlay" for call in approved["toolCalls"])
    final = project_service.get_project(project.id).model_dump(mode="python")
    scene = final["structuredContent"]["episode"]["visualPlan"]["scenes"][0]
    assert scene["metadata"]["videoOverlayIds"]
    assert final["overlays"]["videoOverlays"][0]["assetId"] in scene["metadata"]["videoOverlayIds"]

