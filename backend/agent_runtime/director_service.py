from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from .director_store import DirectorStore
from .pi_transport import FakePiTransport
from .plugin_tools import create_delivery_artifacts, generate_vector_card
from agent.lab_runner.recipe_loader import RecipeValidationError, load_recipe_by_id

REPO_ROOT = Path(__file__).resolve().parents[2]


class DirectorService:
    def __init__(self, store: DirectorStore | None = None, transport: FakePiTransport | None = None):
        self.store = store or DirectorStore()
        self.transport = transport or FakePiTransport()

    def create_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        recipe_id = str(payload.get("recipeId") or "structured-knowledge-video")
        try:
            recipe = load_recipe_by_id(recipe_id, root=REPO_ROOT / "agent" / "recipes")
        except RecipeValidationError as exc:
            raise ValueError(str(exc)) from exc
        run = self.store.create({**payload, "recipeId": recipe.id, "recipeVersion": recipe.version})
        run_id = run["runId"]
        task = run["task"] or "Create a previewable and JianYing-importable video draft from this script."
        session = self.transport.create_session(run_id, task)
        run["piSession"] = session
        run["recipe"] = {
            "id": recipe.id,
            "version": recipe.version,
            "description": recipe.description,
            "stepCount": len(recipe.steps),
        }
        run["messages"].append({"role": "user", "content": task})
        self.store.save(run)
        self.store.append_event(run_id, {"type": "run.created", "status": run["status"], "recipeId": run["recipeId"]})
        self.store.append_event(run_id, {"type": "recipe.loaded", "recipeId": recipe.id, "recipeVersion": recipe.version, "stepCount": len(recipe.steps)})
        for event in self.transport.initial_events(run_id, task):
            self.store.append_event(run_id, event)
        artifact = generate_vector_card(self.store.run_dir(run_id), scene_id="scene_001", title="Director Draft", body=task)
        run["toolCalls"].append({"toolName": "vector_card.generate_scene_asset", "status": "succeeded", "sceneId": "scene_001", "artifactId": artifact["artifactId"]})
        run["artifacts"].append(artifact)
        self.store.append_event(run_id, {"type": "tool.call.succeeded", "toolName": "vector_card.generate_scene_asset", "sceneId": "scene_001"})
        self.store.append_event(run_id, {"type": "artifact.created", "artifact": artifact})
        approval_id = f"approval_{uuid4().hex[:10]}"
        approval = {
            "approvalId": approval_id,
            "operation": "replace_scene_asset",
            "status": "pending",
            "risk": "medium",
            "sceneId": "scene_001",
            "message": "Bind the local vector_card plugin output to Scene 001?",
        }
        run["approvals"].append(approval)
        run["currentApprovalId"] = approval_id
        run["status"] = "waiting_approval"
        self.store.save(run)
        self.store.append_event(run_id, {"type": "approval.requested", "approval": approval})
        return self.get_run(run_id)

    def list_runs(self) -> list[dict[str, Any]]:
        return self.store.list()

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self.store.load(run_id)

    def events(self, run_id: str, after: int = 0) -> list[dict[str, Any]]:
        return self.store.events(run_id, after=after)

    def message(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        run = self.store.load(run_id)
        message = {"role": "user", "content": str(payload.get("message") or payload.get("content") or "").strip()}
        run["messages"].append(message)
        self.store.save(run)
        self.store.append_event(run_id, {"type": "message.created", "message": message})
        return self.get_run(run_id)

    def decide_approval(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        run = self.store.load(run_id)
        approval_id = str(payload.get("approvalId") or run.get("currentApprovalId") or "")
        decision = str(payload.get("decision") or "replace")
        target = next((item for item in run["approvals"] if item.get("approvalId") == approval_id), None)
        if not target:
            raise KeyError("approval_not_found")
        target["status"] = "approved"
        target["decision"] = decision
        run["currentApprovalId"] = None
        self.store.save(run)
        self.store.append_event(run_id, {"type": "approval.resolved", "approvalId": approval_id, "decision": decision})
        return self.resume(run_id)

    def resume(self, run_id: str) -> dict[str, Any]:
        run = self.store.load(run_id)
        if run.get("currentApprovalId"):
            return run
        if run.get("status") == "succeeded":
            return run
        self.store.append_event(run_id, {"type": "run.resumed"})
        self.store.append_event(run_id, {"type": "tool.call.started", "toolName": "visual_scene.bind_generated_asset", "sceneId": "scene_001"})
        run["toolCalls"].append({"toolName": "visual_scene.bind_generated_asset", "status": "succeeded", "sceneId": "scene_001"})
        self.store.append_event(run_id, {"type": "tool.call.succeeded", "toolName": "visual_scene.bind_generated_asset", "sceneId": "scene_001"})
        delivery = create_delivery_artifacts(self.store.run_dir(run_id), run_id)
        run["artifacts"].extend([delivery["preview"], delivery["jianying"]])
        self.store.append_event(run_id, {"type": "artifact.created", "artifact": delivery["preview"]})
        self.store.append_event(run_id, {"type": "artifact.created", "artifact": delivery["jianying"]})
        run["status"] = "succeeded"
        self.store.save(run)
        run["finishedAt"] = run["updatedAt"]
        self.store.save(run)
        self.store.append_event(run_id, {"type": "run.completed", "status": "succeeded"})
        return self.get_run(run_id)

    def cancel(self, run_id: str) -> dict[str, Any]:
        run = self.store.load(run_id)
        run["status"] = "cancelled"
        self.store.save(run)
        self.store.append_event(run_id, {"type": "run.cancelled"})
        return self.get_run(run_id)

    def artifacts(self, run_id: str) -> dict[str, Any]:
        run = self.store.load(run_id)
        return {"runId": run_id, "artifacts": run.get("artifacts", [])}
