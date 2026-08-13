from agent.lab_runner.executor import LabRunner
from agent.lab_runner.recipe_loader import load_recipe_by_id
from agent.lab_runner.run_store import RunStore
from tests.test_video_agent_lab_runner import _tools


def test_three_closed_loop_recipes_with_mocked_external_providers(tmp_path):
    for recipe_id in ["structured-knowledge-video", "existing-assets-recut", "book-summary-short"]:
        recipe = load_recipe_by_id(recipe_id)
        runner = LabRunner(store=RunStore(tmp_path / recipe_id), tools=_tools())
        run = runner.start(recipe, {"id": f"closed-{recipe_id}", "fixtures": {"projectId": "p", "batchId": "b"}, "conditions": {"visual_assets_complete": True}})
        if run["status"] == "waiting_approval":
            decisions = {"approvals": [{"operation": "script_content_change", "decision": "approved"}]}
            run = runner.resume(recipe, run["runId"], {"id": f"closed-{recipe_id}", "fixtures": {"projectId": "p", "batchId": "b"}, "conditions": {"visual_assets_complete": True}}, decisions)
        assert run["status"] == "succeeded"
        assert run["providerCalls"]["fish"] == 0
