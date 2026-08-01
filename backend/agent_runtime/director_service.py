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
from .production_packs import renderer_registry
from agent.lab_runner.recipe_loader import RecipeValidationError, load_recipe_by_id
from vforge.client import VForgeError, bind_scene_assets
from routers.visual_assets import CodeVisualRenderBody, regenerate_code_visual_scene

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
        if isinstance(payload.get("intake"), dict):
            run["intake"] = payload["intake"]
            self.store.save(run)
        if isinstance(payload.get("directorPack"), dict):
            run["directorPack"] = payload["directorPack"]
            run["skills"] = payload.get("skills") if isinstance(payload.get("skills"), list) else []
            self.store.save(run)
        if isinstance(payload.get("scenePlan"), dict):
            run["scenePlan"] = payload["scenePlan"]
            self.store.save(run)
        if isinstance(payload.get("productionPack"), dict):
            run["productionPack"] = payload["productionPack"]
            run["rendererDispatches"] = []
            self.store.save(run)
        factory_context = payload.get("factoryContext")
        if isinstance(factory_context, dict):
            run["factoryContext"] = factory_context
            self.store.save(run)
        run_id = run["runId"]
        task = run["task"] or "Create a previewable and JianYing-importable video draft from this script."
        target_scene_id = self._target_scene_id(payload)
        pi_prompt = f"{task}\n\n{proposal_instruction(target_scene_id)}"
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
        if isinstance(run.get("scenePlan"), dict):
            self.store.append_event(run_id, {"type": "scene_plan.proposed", "packId": (run.get("directorPack") or {}).get("packId"), "sceneCount": len(run["scenePlan"].get("scenes") or []), "styleSignature": run["scenePlan"].get("styleSignature")})
        self.store.append_event(run_id, {"type": "recipe.loaded", "recipeId": recipe.id, "recipeVersion": recipe.version, "stepCount": len(recipe.steps)})
        for event in self.transport.initial_events(run_id, task):
            self.store.append_event(run_id, event)
        has_compiled_visual_specs = any(
            isinstance(scene, dict) and isinstance(scene.get("visualSpec"), dict)
            for scene in (run.get("scenePlan") or {}).get("scenes") or []
        )
        if has_compiled_visual_specs:
            # A V2 Production Pack must not be shadowed by the legacy sample
            # vector card.  Its only render artifacts are produced after the
            # approval gate by the selected real Renderer.
            self.store.append_event(run_id, {"type": "visual_spec.compile.ready", "sceneCount": len((run.get("scenePlan") or {}).get("scenes") or [])})
        else:
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
            "sceneId": target_scene_id,
            "message": f"Generate and bind the approved Code Visual picture-in-picture to {target_scene_id}?",
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

    @staticmethod
    def _target_scene_id(payload: dict[str, Any]) -> str:
        scene_plan = payload.get("scenePlan") if isinstance(payload.get("scenePlan"), dict) else {}
        proposed = scene_plan.get("scenes") if isinstance(scene_plan, dict) else None
        if isinstance(proposed, list) and proposed and isinstance(proposed[0], dict) and proposed[0].get("sceneId"):
            return str(proposed[0]["sceneId"])
        intake = payload.get("intake") if isinstance(payload.get("intake"), dict) else {}
        structured = intake.get("structuredContent") if isinstance(intake, dict) else None
        episode = structured.get("episode") if isinstance(structured, dict) else None
        plan = episode.get("visualPlan") if isinstance(episode, dict) else None
        scenes = plan.get("scenes") if isinstance(plan, dict) else None
        if isinstance(scenes, list) and scenes and isinstance(scenes[0], dict) and scenes[0].get("id"):
            return str(scenes[0]["id"])
        return "scene_001"

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
        project_id, fallback_scene_id = self._project_target(run)
        scene_rows = list((run.get("scenePlan") or {}).get("scenes") or [])
        visual_rows = [row for row in scene_rows if isinstance(row, dict) and isinstance(row.get("visualSpec"), dict)]
        if visual_rows and not project_id:
            run["status"] = "recoverable"
            error = {
                "code": "production_pack_project_required",
                "message": "Production Pack renders require an existing VideoForge project target.",
                "recoverable": True,
                "details": {"recovery": "Select an existing project, then create a new Director Run so generated assets can be bound into Preview."},
            }
            run["errors"].append(error)
            self.store.save(run)
            self.store.append_event(run_id, {"type": "renderer.dispatch.failed", **error})
            return self.get_run(run_id)
        production_dispatch = bool(project_id and visual_rows)
        bound_asset_ids: list[str] = []
        if project_id and visual_rows:
            registry_index = {
                (str(entry.get("providerId")), str(entry.get("rendererId"))): entry
                for entry in renderer_registry().get("renderers") or []
                if isinstance(entry, dict)
            }
            for row in visual_rows:
                spec = dict(row["visualSpec"])
                scene_id = str(spec.get("sceneId") or row.get("sceneId") or fallback_scene_id)
                renderer_entry = registry_index.get((str(spec.get("providerId")), str(spec.get("rendererId"))))
                if not renderer_entry:
                    run["status"] = "recoverable"
                    error = {"code": "renderer_not_registered", "message": f"Renderer unavailable: {spec.get('providerId')}/{spec.get('rendererId')}", "recoverable": True, "details": {"sceneId": scene_id}}
                    run["errors"].append(error)
                    self.store.save(run)
                    self.store.append_event(run_id, {"type": "renderer.dispatch.failed", **error})
                    return self.get_run(run_id)
                missing = list(renderer_entry.get("missingDependencies") or [])
                if renderer_entry.get("availability") != "available":
                    run["status"] = "recoverable"
                    error = {"code": "renderer_dependency_missing", "message": "Renderer dependency is unavailable.", "recoverable": True, "details": {"sceneId": scene_id, "missingDependencies": missing, "recovery": "Install the listed local dependency and resume this run."}}
                    run["errors"].append(error)
                    self.store.save(run)
                    self.store.append_event(run_id, {"type": "renderer.dispatch.failed", **error})
                    return self.get_run(run_id)
                dispatch = {
                    "sceneId": scene_id,
                    "packId": spec.get("packId"),
                    "packVersion": spec.get("packVersion"),
                    "packFingerprint": spec.get("packFingerprint"),
                    "providerId": spec.get("providerId"),
                    "rendererId": spec.get("rendererId"),
                    "templateId": spec.get("templateId"),
                    "visualSpec": spec,
                    "status": "started",
                }
                run.setdefault("rendererDispatches", []).append(dispatch)
                self.store.save(run)
                self.store.append_event(run_id, {"type": "visual_spec.selected", "sceneId": scene_id, "visualSpec": spec})
                self.store.append_event(run_id, {"type": "renderer.dispatch.started", "sceneId": scene_id, "providerId": spec.get("providerId"), "rendererId": spec.get("rendererId"), "templateId": spec.get("templateId")})
                try:
                    params = spec.get("parameters") if isinstance(spec.get("parameters"), dict) else {}
                    result = regenerate_code_visual_scene(
                        project_id,
                        scene_id,
                        CodeVisualRenderBody(
                            sourceMode="visual_plan",
                            sceneIds=[scene_id],
                            exportPng=spec.get("outputMode") in {"png", "video", "transparent_sequence"},
                            exportVideo=spec.get("outputMode") in {"video", "transparent_sequence"},
                            exportTransparentVideo=spec.get("outputMode") == "transparent_sequence",
                            bindToProject=True,
                            rendererId=str(spec["rendererId"]),
                            themeMode=str(spec["themeMode"]),
                            presentationMode=str(spec["presentationMode"]),
                            visualFamily=str(params.get("visualFamily") or "evidence"),
                            ipPack=str(params.get("ipPack") or "neutral"),
                            videoFps=int(params.get("videoFps") or 12),
                            overlayX=float(params.get("overlayX") or 0.5),
                            overlayY=float(params.get("overlayY") or 0.32),
                            overlayScale=float(params.get("overlayScale") or 0.36),
                            overlayOpacity=float(params.get("overlayOpacity") or 1),
                            overlayZIndex=int(params.get("overlayZIndex") or 0),
                            productionPack={"packId": spec.get("packId"), "packVersion": spec.get("packVersion"), "packFingerprint": spec.get("packFingerprint"), "archetypeId": spec.get("archetypeId"), "rendererBindingId": spec.get("rendererBindingId"), "visualSpec": spec},
                        ),
                    )
                except Exception as exc:
                    dispatch.update({"status": "failed", "error": str(exc)})
                    run["status"] = "recoverable"
                    error = {"code": "renderer_dispatch_failed", "message": str(exc), "recoverable": True, "details": {"sceneId": scene_id, "rendererId": spec.get("rendererId"), "recovery": "Resolve the renderer error and resume this Director Run."}}
                    run["errors"].append(error)
                    self.store.save(run)
                    self.store.append_event(run_id, {"type": "renderer.dispatch.failed", **error})
                    return self.get_run(run_id)
                artifacts = []
                for exported in result.get("videoExports", []):
                    artifact = {
                        "artifactId": f"production_pack_{scene_id}_{Path(str(exported.get('videoPath') or '')).stem}",
                        "artifactType": "production_pack_video",
                        "path": exported.get("videoPath"),
                        "sha256": exported.get("videoSha256"),
                        "sceneId": scene_id,
                        "packId": spec.get("packId"),
                        "packFingerprint": spec.get("packFingerprint"),
                        "rendererId": spec.get("rendererId"),
                        "templateId": spec.get("templateId"),
                    }
                    artifacts.append(artifact)
                if not artifacts:
                    for item in result.get("items", []):
                        if str(item.get("segmentId") or "") == scene_id and item.get("svgPath"):
                            artifacts.append({
                                "artifactId": f"production_pack_{scene_id}_svg",
                                "artifactType": "production_pack_svg",
                                "path": item.get("svgPath"),
                                "sha256": item.get("svgSha256"),
                                "sceneId": scene_id,
                                "packId": spec.get("packId"),
                                "packFingerprint": spec.get("packFingerprint"),
                                "rendererId": spec.get("rendererId"),
                                "templateId": spec.get("templateId"),
                            })
                run["artifacts"].extend(artifacts)
                binding_rows = result.get("bindings", [])
                bound_asset_ids.extend(str(binding.get("assetId")) for binding in binding_rows if isinstance(binding, dict) and binding.get("assetId"))
                dispatch.update({"status": "succeeded", "artifacts": artifacts, "bindings": binding_rows})
                self.store.save(run)
                self.store.append_event(run_id, {"type": "artifact.bound", "sceneId": scene_id, "artifacts": artifacts, "bindings": binding_rows})
                self.store.append_event(run_id, {"type": "renderer.dispatch.completed", "sceneId": scene_id, "providerId": spec.get("providerId"), "rendererId": spec.get("rendererId"), "artifacts": artifacts})
        elif project_id and (run.get("productionPack") or run.get("directorPack")):
            run["status"] = "recoverable"
            error = {"code": "visual_spec_missing", "message": "Production Pack Run has no compiled VisualSpec.", "recoverable": True, "details": {"recovery": "Recompile the Pack and create a new Director Run."}}
            run["errors"].append(error)
            self.store.save(run)
            self.store.append_event(run_id, {"type": "renderer.dispatch.failed", **error})
            return self.get_run(run_id)

        recipe = load_recipe_by_id(run["recipeId"], root=REPO_ROOT / "agent" / "recipes")
        if production_dispatch:
            actual_artifact_id = bound_asset_ids[0] if bound_asset_ids else next(
                (str(item.get("artifactId")) for item in run.get("artifacts", []) if isinstance(item, dict) and str(item.get("artifactId") or "").startswith("production_pack_")),
                "production_pack_project_binding",
            )
            record_binding_action(self.store, run, recipe, artifact_id=actual_artifact_id)
        else:
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
        bound_scene_id = str((visual_rows[0].get("sceneId") if production_dispatch and visual_rows else None) or "scene_001")
        self.store.append_event(run_id, {"type": "tool.call.started", "toolName": "visual_scene.bind_generated_asset", "sceneId": bound_scene_id})
        run["toolCalls"].append({"toolName": "visual_scene.bind_generated_asset", "status": "succeeded", "sceneId": bound_scene_id, "assetIds": bound_asset_ids if production_dispatch else []})
        self.store.append_event(run_id, {"type": "tool.call.succeeded", "toolName": "visual_scene.bind_generated_asset", "sceneId": bound_scene_id})
        if production_dispatch:
            self.store.append_event(run_id, {"type": "project.preview.updated", "projectId": project_id, "assetIds": bound_asset_ids, "source": "production_pack"})
        else:
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

    @staticmethod
    def _project_target(run: dict[str, Any]) -> tuple[str | None, str]:
        intake = run.get("intake") if isinstance(run.get("intake"), dict) else {}
        source = intake.get("source") if isinstance(intake, dict) else {}
        project_id = str(source.get("projectId") or "").strip() if isinstance(source, dict) else ""
        approval = next((item for item in run.get("approvals", []) if item.get("status") == "approved"), None)
        return (project_id or None, str((approval or {}).get("sceneId") or "scene_001"))

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
                    approval = next((item for item in run.get("approvals", []) if item.get("status") == "pending"), {})
                    scene_id = str(approval.get("sceneId") or "scene_001")
                    proposals = merge_action_proposals(run, proposals_from_agent_end(event, scene_id=scene_id))
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
