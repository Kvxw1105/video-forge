from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .artifact_registry import ArtifactRegistry
from .models import Recipe, RecipeStep
from .policy_checker import PolicyChecker
from .run_store import RunStore, now_iso
from .tool_registry import ToolRegistry


class LabRunner:
    def __init__(
        self,
        store: RunStore | None = None,
        tools: ToolRegistry | None = None,
        policy: PolicyChecker | None = None,
    ):
        self.store = store or RunStore()
        self.tools = tools or ToolRegistry()
        self.policy = policy or PolicyChecker()

    def plan(self, recipe: Recipe, case: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "recipeId": recipe.id,
            "recipeVersion": recipe.version,
            "caseId": (case or {}).get("id"),
            "steps": [
                {
                    "stepId": step.id,
                    "kind": step.kind,
                    "tool": step.tool,
                    "policy": step.policy,
                    "inputFrom": step.inputFrom,
                    "completionCondition": step.completionCondition,
                }
                for step in recipe.steps
            ],
        }

    def start(self, recipe: Recipe, case: dict[str, Any] | None = None) -> dict[str, Any]:
        run = self.store.create(recipe.id, recipe.version, (case or {}).get("id"))
        self.store.append_event(run["runId"], {"type": "run.started", "recipeId": recipe.id})
        return self._execute(recipe, case or {}, run)

    def resume(self, recipe: Recipe, run_id: str, case: dict[str, Any] | None = None, decisions: dict[str, Any] | None = None) -> dict[str, Any]:
        if decisions:
            self.store.save_decisions(run_id, decisions)
        run = self.store.load(run_id)
        self.store.append_event(run_id, {"type": "run.resumed"})
        return self._execute(recipe, case or {}, run)

    def _execute(self, recipe: Recipe, case: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
        artifacts = ArtifactRegistry(self.store.run_dir(run["runId"]))
        completed = {step["stepId"] for step in run["steps"] if step.get("status") == "succeeded"}
        for step in recipe.steps:
            if step.id in completed:
                continue
            if not set(step.inputFrom).issubset(completed):
                run["status"] = "recoverable"
                run["currentStepId"] = step.id
                run["errors"].append({"code": "dependency_incomplete", "message": f"{step.id} dependencies are incomplete", "recoverable": True})
                self.store.save(run)
                return run
            run["currentStepId"] = step.id
            self.store.append_event(run["runId"], {"type": "step.started", "stepId": step.id, "kind": step.kind})
            if step.kind in {"inspection", "evaluation"} and not step.tool:
                ref = artifacts.add(step.produces[0] if step.produces else step.id, {"status": "succeeded", "stepId": step.id}, source=step.id)
                self._mark_step(run, step, "succeeded", [ref])
                completed.add(step.id)
                continue
            if step.kind == "approval":
                decision = self.policy.decide(step.policy or "script_content_change", case.get("policyContext") or {})
                approved = self._is_approved(run["runId"], step.policy or step.id)
                approval = {"operation": step.policy or step.id, "status": "approved" if approved else decision.decision, "risk": decision.risk, "policyId": decision.policyId}
                if approval not in run["approvals"]:
                    run["approvals"].append(approval)
                if decision.decision == "deny":
                    self._mark_step(run, step, "failed", [], "policy_denied")
                    run["status"] = "failed"
                    self.store.save(run)
                    return run
                if decision.decision == "approval_required" and not approved:
                    self._mark_step(run, step, "waiting", [], "approval_required")
                    run["status"] = "waiting_approval"
                    self.store.save(run)
                    self.store.append_event(run["runId"], {"type": "approval.requested", "operation": approval["operation"]})
                    return run
                self._mark_step(run, step, "succeeded", [])
                completed.add(step.id)
                continue
            if step.kind == "wait":
                if not self._condition_met(step.condition or step.completionCondition, case, run):
                    self._mark_step(run, step, "waiting", [], "waiting_assets")
                    run["status"] = "waiting_assets"
                    self.store.save(run)
                    self.store.append_event(run["runId"], {"type": "run.waiting_assets", "stepId": step.id})
                    return run
                self._mark_step(run, step, "succeeded", [])
                completed.add(step.id)
                continue
            if step.kind in {"tool", "evaluation"} and step.tool:
                result = self._call_tool(step, case, run)
                if result.get("status") == "waiting_approval":
                    self._mark_step(run, step, "waiting", [], result.get("errorCode"))
                    run["status"] = "waiting_approval"
                    self.store.save(run)
                    return run
                if result.get("status") == "failed":
                    self._mark_step(run, step, "failed", [], result.get("errorCode"))
                    run["status"] = "recoverable" if step.onError == "recoverable" else "failed"
                    self.store.save(run)
                    return run
                ref = artifacts.add(step.produces[0] if step.produces else (step.tool or step.id), result.get("result"), source=step.id)
                self._mark_step(run, step, "succeeded", [ref])
                completed.add(step.id)
                self._update_known_ids(run, result.get("result"))
                continue
        run["status"] = "succeeded"
        run["finishedAt"] = now_iso()
        run["currentStepId"] = None
        self.store.save(run)
        self.store.save_eval(run["runId"], self._eval_summary(run, case))
        self.store.append_event(run["runId"], {"type": "run.completed"})
        return run

    def _call_tool(self, step: RecipeStep, case: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
        assert step.tool
        key = self._idempotency_key(run["runId"], step.id, step.tool)
        existing = next((call for call in run["toolCalls"] if call.get("idempotencyKey") == key and call.get("status") == "succeeded"), None)
        if existing:
            reused = {"status": "succeeded", "result": {"reused": True, "resultArtifactRef": existing.get("resultArtifactRef")}}
            run["toolCalls"].append({**existing, "reused": True})
            return reused
        kwargs = self._tool_kwargs(step.tool, case, run)
        started = now_iso()
        try:
            result = self.tools.call(step.tool, **kwargs)
            call = {"toolName": step.tool, "idempotencyKey": key, "status": "succeeded", "reused": False, "startedAt": started, "finishedAt": now_iso(), "resultArtifactRef": None, "errorCode": None}
            run["toolCalls"].append(call)
            return {"status": "succeeded", "result": result}
        except Exception as exc:
            code = getattr(exc, "detail", None)
            if isinstance(code, dict):
                code = code.get("code") or code.get("message")
            code = str(code or exc)
            run["toolCalls"].append({"toolName": step.tool, "idempotencyKey": key, "status": "failed", "reused": False, "startedAt": started, "finishedAt": now_iso(), "resultArtifactRef": None, "errorCode": code})
            if code == "asset_conflict":
                return {"status": "waiting_approval", "errorCode": "asset_conflict"}
            return {"status": "failed", "errorCode": code}

    def _tool_kwargs(self, tool: str, case: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
        inputs = case.get("toolInputs", {})
        if tool in inputs:
            return dict(inputs[tool])
        project_id = run.get("projectId") or case.get("projectId") or case.get("fixtures", {}).get("projectId") or "synthetic_project"
        batch_id = run.get("batchId") or case.get("batchId") or case.get("fixtures", {}).get("batchId") or "synthetic_batch"
        item_id = case.get("itemId") or case.get("fixtures", {}).get("itemId") or "item_a"
        if tool in {"inspect_video_project", "inspect_video_readiness", "validate_video_readiness", "build_video_preview", "audit_video_preview", "export_editable_draft", "prepare_visual_generation_pack"}:
            return {"pid": project_id}
        if tool == "prepare_structured_script":
            return {"spec": case.get("scriptSpec") or {"text": case.get("sourceText", "synthetic script")}}
        if tool == "create_video_factory_job":
            return {"spec": case.get("batchSpec") or {"batchId": batch_id, "schemaVersion": 1}}
        if tool in {"inspect_pending_visuals", "recover_video_job", "get_video_job_status"}:
            return {"batch_id": batch_id}
        if tool in {"bind_scene_assets"}:
            return {"batch_id": batch_id, "item_id": item_id, "data": case.get("bindingData") or {"folder": "artifact://visuals"}}
        if tool == "validate_video_assets":
            return {"batch_id": batch_id, "item_id": item_id}
        if tool == "review_visual_scene_plan":
            return {"pid": project_id}
        return {}

    def _mark_step(self, run: dict[str, Any], step: RecipeStep, status: str, refs: list[str], error: str | None = None) -> None:
        existing = next((item for item in run["steps"] if item.get("stepId") == step.id and item.get("status") in {"waiting", "failed"}), None)
        row = existing or {"stepId": step.id, "kind": step.kind, "status": status, "attempt": 0, "startedAt": now_iso(), "finishedAt": None, "inputArtifactRefs": [], "outputArtifactRefs": [], "errorCode": None}
        row["attempt"] += 1
        row["status"] = status
        row["outputArtifactRefs"] = refs
        row["errorCode"] = error
        if status == "succeeded":
            row["finishedAt"] = now_iso()
        if existing is None:
            run["steps"].append(row)
        self.store.append_event(run["runId"], {"type": f"step.{status}", "stepId": step.id, "errorCode": error})

    def _condition_met(self, condition: str, case: dict[str, Any], run: dict[str, Any]) -> bool:
        conditions = case.get("conditions") or {}
        return bool(conditions.get(condition) or conditions.get("visual_assets_complete") or conditions.get("coverage_complete"))

    def _is_approved(self, run_id: str, operation: str) -> bool:
        decisions = self.store.load_decisions(run_id)
        return any(item.get("operation") == operation and item.get("decision") == "approved" for item in decisions.get("approvals", []))

    def _idempotency_key(self, run_id: str, step_id: str, tool: str) -> str:
        return hashlib.sha256(f"{run_id}:{step_id}:{tool}".encode("utf-8")).hexdigest()[:24]

    def _update_known_ids(self, run: dict[str, Any], result: Any) -> None:
        if isinstance(result, dict):
            run["projectId"] = run.get("projectId") or result.get("projectId")
            run["batchId"] = run.get("batchId") or result.get("batchId")

    def _eval_summary(self, run: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
        return {
            "runId": run["runId"],
            "caseId": run.get("caseId"),
            "recipeId": run["recipeId"],
            "status": run["status"],
            "executionLevel": case.get("executionLevel", "static"),
            "stateTransitions": [step["status"] for step in run["steps"]],
            "toolCallCount": len(run["toolCalls"]),
            "approvalCount": len(run["approvals"]),
            "fishNetworkCalls": run.get("providerCalls", {}).get("fish", 0),
        }
