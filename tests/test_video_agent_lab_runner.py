from agent.lab_runner.executor import LabRunner
from agent.lab_runner.recipe_loader import load_recipe_by_id
from agent.lab_runner.run_store import RunStore
from agent.lab_runner.tool_registry import ToolRegistry


def _tools():
    return ToolRegistry(
        {
            "inspect_video_project": lambda pid: {"projectId": pid},
            "inspect_video_readiness": lambda pid: {"projectId": pid, "ready": True},
            "validate_video_readiness": lambda pid: {"projectId": pid, "ready": True},
            "prepare_structured_script": lambda spec: {"proposal": spec},
            "create_video_factory_job": lambda spec: {"batchId": spec.get("batchId", "b")},
            "review_visual_scene_plan": lambda pid: {"projectId": pid, "scenes": [{"sceneId": "s1"}]},
            "prepare_visual_generation_pack": lambda pid: {"projectId": pid, "pack": []},
            "inspect_pending_visuals": lambda batch_id: {"batchId": batch_id, "items": []},
            "bind_scene_assets": lambda batch_id, item_id, data: {"batchId": batch_id, "itemId": item_id},
            "validate_video_assets": lambda batch_id, item_id: {"batchId": batch_id, "itemId": item_id, "ok": True},
            "build_video_preview": lambda pid: {"projectId": pid, "preview": "artifact://preview/1"},
            "audit_video_preview": lambda pid: {"projectId": pid, "result": "passed"},
            "export_editable_draft": lambda pid: {"projectId": pid, "policy": "create_new"},
            "recover_video_job": lambda batch_id: {"batchId": batch_id, "status": "resumed"},
            "get_video_job_status": lambda batch_id: {"batchId": batch_id, "status": "running"},
        }
    )


def test_waiting_assets_and_resume(tmp_path):
    recipe = load_recipe_by_id("structured-knowledge-video")
    runner = LabRunner(store=RunStore(tmp_path), tools=_tools())
    first = runner.start(recipe, {"id": "case", "fixtures": {"projectId": "p", "batchId": "b"}, "conditions": {}})
    assert first["status"] == "waiting_approval"
    decisions = {"approvals": [{"operation": "script_content_change", "decision": "approved"}]}
    second = runner.resume(recipe, first["runId"], {"id": "case", "fixtures": {"projectId": "p", "batchId": "b"}, "conditions": {}}, decisions)
    assert second["status"] == "waiting_assets"
    third = runner.resume(recipe, first["runId"], {"id": "case", "fixtures": {"projectId": "p", "batchId": "b"}, "conditions": {"visual_assets_complete": True}}, decisions)
    assert third["status"] == "succeeded"


def test_successful_step_not_rerun_on_resume(tmp_path):
    calls = {"inspect": 0}
    tools = _tools()
    tools.tools["inspect_video_project"] = lambda pid: calls.__setitem__("inspect", calls["inspect"] + 1) or {"projectId": pid}
    recipe = load_recipe_by_id("existing-assets-recut")
    runner = LabRunner(store=RunStore(tmp_path), tools=tools)
    run = runner.start(recipe, {"id": "case", "fixtures": {"projectId": "p", "batchId": "b"}, "conditions": {}})
    runner.resume(recipe, run["runId"], {"id": "case", "fixtures": {"projectId": "p", "batchId": "b"}, "conditions": {"visual_assets_complete": True}})
    assert calls["inspect"] == 1
