from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from .director_store import DirectorStore
from .director_proposals import merge_action_proposals, proposal_instruction, proposals_from_agent_end
from .lab_actions import dispatch_factory_binding, record_binding_action
from .pi_transport import FakePiTransport, PiRpcError, PiRpcTransport
from .plugin_tools import create_delivery_artifacts, generate_vector_card
from agent.lab_runner.recipe_loader import RecipeValidationError, load_recipe_by_id
from vforge.client import VForgeError, bind_scene_assets

REPO_ROOT = Path(__file__).resolve().parents[2]


class DirectorService:
    def __init__(self, store: DirectorStore | None = None, transport: Any | None = None, factory_binder: Any | None = None):
        self.store = store or DirectorStore()
        self._state_lock = threading.RLock()
        self.factory_binder = factory_binder or bind_scene_assets
        if transport is not None:
            self.transport = transport
            set_event_sink = getattr(self.transport, "set_event_sink", None)
            if set_event_sink:
                set_event_sink(self._on_pi_event)
        elif os.getenv("VIDEOFORGE_PI_TRANSPORT", "fake").lower() == "rpc":
            self.transport = PiRpcTransport.from_environment(run_dir=self.store.run_dir, repo_root=REPO_ROOT, event_sink=self._on_pi_event)
        else:
            self.transport = FakePiTransport()

    def create_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        recipe_id = str(payload.get("recipeId") or "structured-knowledge-video")
        try:
            recipe = load_recipe_by_id(recipe_id, root=REPO_ROOT / "agent" / "recipes")
        except RecipeValidationError as exc:
            raise ValueError(str(exc)) from exc
        run = self.store.create({**payload, "recipeId": recipe.id, "recipeVersion": recipe.version})
        factory_context = payload.get("factoryContext")
        if isinstance(factory_context, dict):
            run["factoryContext"] = factory_context
            self.store.save(run)
        run_id = run["runId"]
        task = run["task"] or "Create a previewable and JianYing-importable video draft from this script."
        pi_prompt = f"{task}\n\n{proposal_instruction()}"
        session = self.transport.create_session(run_id, pi_prompt)
        run["piSession"] = session
        run["piState"] = "starting"
        run["transport"] = self.transport.name
        run["mockTransport"] = bool(session.get("mockTransport"))
        run["liveCallPerformed"] = bool(session.get("liveCallPerformed"))
        run["networkCalls"] = session.get("networkCalls")
        run["metrics"] = {
            "mockTransport": run["mockTransport"],
            "liveCallPerformed": run["liveCallPerformed"],
            "networkCalls": run["networkCalls"],
        }
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
            "recipeStepId": "bind_assets",
            "recipeTool": "bind_scene_assets",
        }
        run["approvals"].append(approval)
        run["currentApprovalId"] = approval_id
        run["status"] = "waiting_approval"
        self.store.save(run)
        self.store.append_event(run_id, {"type": "approval.requested", "approval": approval})
        # The approval exists before Pi can emit agent_end, so a proposal can
        # only enrich this gate and never become a detached executable action.
        prompt = getattr(self.transport, "prompt", None)
        if prompt:
            with self._state_lock:
                run = self.store.load(run_id)
                run["piState"] = "running"
                self.store.save(run)
            try:
                prompt_result = prompt(run_id, pi_prompt)
            except PiRpcError as exc:
                run = self.store.load(run_id)
                run["piState"] = "failed"
                run["status"] = "recoverable"
                run["errors"].append({"code": "pi_prompt_failed", "message": str(exc), "recoverable": True})
                self.store.save(run)
                self.store.append_event(run_id, {"type": "pi.prompt.failed", "errorCode": "pi_prompt_failed"})
                return self.get_run(run_id)
            with self._state_lock:
                run = self.store.load(run_id)
                run["piPromptAccepted"] = bool(prompt_result.get("accepted"))
                if prompt_result.get("settled"):
                    run["piState"] = "settled"
                run["liveCallPerformed"] = bool(run["liveCallPerformed"] or not run["mockTransport"])
                run["metrics"]["liveCallPerformed"] = run["liveCallPerformed"]
                self.store.save(run)
                is_settled = run["piState"] == "settled"
            self.store.append_event(run_id, {"type": "pi.prompt.accepted", "settled": is_settled})
            if is_settled:
                self.store.append_event(run_id, {"type": "agent.settled", "transport": self.transport.name})
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
        follow_up = getattr(self.transport, "follow_up", None)
        if follow_up and message["content"]:
            follow_up(run_id, message["content"])
        return self.get_run(run_id)

    def decide_approval(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        run = self.store.load(run_id)
        approval_id = str(payload.get("approvalId") or run.get("currentApprovalId") or "")
        decision = str(payload.get("decision") or "replace")
        target = next((item for item in run["approvals"] if item.get("approvalId") == approval_id), None)
        if not target:
            raise KeyError("approval_not_found")
        target["decision"] = decision
        run["currentApprovalId"] = None
        proposal = target.get("actionProposal")
        is_approved = decision in {"replace", "approve", "approved"}
        target["status"] = "approved" if is_approved else "rejected"
        if isinstance(proposal, dict):
            proposal["status"] = "approved" if is_approved else "rejected"
            proposal_id = proposal.get("proposalId")
            for item in run.get("actionProposals", []):
                if item.get("proposalId") == proposal_id:
                    item["status"] = proposal["status"]
        self.store.save(run)
        self.store.append_event(run_id, {"type": "approval.resolved", "approvalId": approval_id, "decision": decision})
        if not is_approved:
            run["status"] = "rejected"
            run["waitingReason"] = "approval_rejected"
            self.store.save(run)
            self.store.append_event(run_id, {"type": "run.rejected", "approvalId": approval_id})
            return self.get_run(run_id)
        return self.resume(run_id)

    def resume(self, run_id: str) -> dict[str, Any]:
        run = self.store.load(run_id)
        if run.get("currentApprovalId"):
            return run
        if run.get("status") == "succeeded":
            return run
        if run.get("piState") != "settled":
            run["status"] = "waiting_pi"
            run["waitingReason"] = "pi_agent_settled"
            self.store.save(run)
            self.store.append_event(run_id, {"type": "lab.action.waiting_for_pi", "stepId": "bind_assets", "piState": run.get("piState")})
            return self.get_run(run_id)
        self.store.append_event(run_id, {"type": "run.resumed"})
        recipe = load_recipe_by_id(run["recipeId"], root=REPO_ROOT / "agent" / "recipes")
        record_binding_action(self.store, run, recipe, artifact_id="artifact_scene_001_vector_card")
        self.store.save(run)
        factory_context = run.get("factoryContext")
        if isinstance(factory_context, dict):
            try:
                self.store.append_event(run_id, {"type": "lab.action.dispatch_started", "stepId": "bind_assets", "toolName": "bind_scene_assets"})
                factory_result = dispatch_factory_binding(factory_context, self.factory_binder)
            except (ValueError, OSError, VForgeError) as exc:
                run["status"] = "recoverable"
                run["errors"].append({"code": str(exc), "recoverable": True})
                self.store.save(run)
                self.store.append_event(run_id, {"type": "lab.action.dispatch_failed", "stepId": "bind_assets", "errorCode": str(exc)})
                return self.get_run(run_id)
            run["labActions"][-1]["factoryResult"] = factory_result
            self.store.save(run)
            self.store.append_event(run_id, {"type": "lab.action.dispatched", "stepId": "bind_assets", "toolName": "bind_scene_assets"})
        self.store.append_event(run_id, {"type": "tool.call.started", "toolName": "visual_scene.bind_generated_asset", "sceneId": "scene_001"})
        run["toolCalls"].append({"toolName": "visual_scene.bind_generated_asset", "status": "succeeded", "sceneId": "scene_001"})
        self.store.append_event(run_id, {"type": "tool.call.succeeded", "toolName": "visual_scene.bind_generated_asset", "sceneId": "scene_001"})
        delivery = create_delivery_artifacts(self.store.run_dir(run_id), run_id)
        run["artifacts"].extend([delivery["preview"], delivery["jianying"]])
        self.store.append_event(run_id, {"type": "artifact.created", "artifact": delivery["preview"]})
        self.store.append_event(run_id, {"type": "artifact.created", "artifact": delivery["jianying"]})
        run["status"] = "succeeded"
        for proposal in run.get("actionProposals", []):
            if proposal.get("status") == "approved":
                proposal["status"] = "completed"
        self.store.save(run)
        run["finishedAt"] = run["updatedAt"]
        self.store.save(run)
        self.store.append_event(run_id, {"type": "run.completed", "status": "succeeded"})
        return self.get_run(run_id)

    def _on_pi_event(self, run_id: str, event: dict[str, Any]) -> None:
        """Persist asynchronous Pi events in the same ordered RunStore stream."""
        should_resume = False
        try:
            with self._state_lock:
                self.store.append_event(run_id, event)
                if event.get("type") == "agent.settled" or event.get("piEventType") == "agent_end":
                    run = self.store.load(run_id)
                if event.get("type") == "agent.settled":
                    run["piState"] = "settled"
                    self.store.save(run)
                    should_resume = run.get("status") == "waiting_pi" and not run.get("currentApprovalId")
                elif event.get("piEventType") == "agent_end":
                    proposals = merge_action_proposals(run, proposals_from_agent_end(event))
                    if proposals:
                        self.store.save(run)
                        for proposal in proposals:
                            self.store.append_event(run_id, {"type": "approval.proposed", "proposal": proposal})
        except FileNotFoundError:
            # A process can finish its final stdout flush after a failed create;
            # never let that background callback crash the Pi reader thread.
            return
        if should_resume:
            self.resume(run_id)

    def cancel(self, run_id: str) -> dict[str, Any]:
        run = self.store.load(run_id)
        abort = getattr(self.transport, "abort", None)
        if abort:
            abort(run_id)
        shutdown = getattr(self.transport, "shutdown", None)
        if shutdown:
            shutdown(run_id)
        run["piState"] = "cancelled"
        run["status"] = "cancelled"
        self.store.save(run)
        self.store.append_event(run_id, {"type": "run.cancelled"})
        return self.get_run(run_id)

    def artifacts(self, run_id: str) -> dict[str, Any]:
        run = self.store.load(run_id)
        return {"runId": run_id, "artifacts": run.get("artifacts", [])}
