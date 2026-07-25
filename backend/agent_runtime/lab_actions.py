from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent.lab_runner.models import Recipe


def binding_action(recipe: Recipe) -> dict[str, Any]:
    """Return the approved Lab step contract for generated-asset binding."""
    step = next((item for item in recipe.steps if item.id == "bind_assets"), None)
    if step is None or step.tool != "bind_scene_assets":
        raise ValueError("recipe_missing_bind_assets_step")
    return {
        "stepId": step.id,
        "kind": step.kind,
        "tool": step.tool,
        "completionCondition": step.completionCondition,
        "policy": "replace_scene_asset",
    }


def record_binding_action(store: Any, run: dict[str, Any], recipe: Recipe, *, artifact_id: str) -> dict[str, Any]:
    """Record one approval-gated Lab action without claiming full Factory completion."""
    action = binding_action(recipe)
    action.update({"status": "succeeded", "artifactId": artifact_id})
    run.setdefault("labActions", []).append(action)
    store.save(run)
    store.append_event(run["runId"], {"type": "lab.action.started", "action": {key: action[key] for key in ("stepId", "tool", "policy")}})
    store.append_event(run["runId"], {"type": "lab.action.succeeded", "action": action})
    return action


def dispatch_factory_binding(context: dict[str, Any], bind_scene_assets: Callable[..., dict[str, Any]]) -> dict[str, Any]:
    """Call the existing Factory binding API only with explicit Director context."""
    batch_id = str(context.get("batchId") or "").strip()
    item_id = str(context.get("itemId") or "").strip()
    data = context.get("data")
    if not batch_id or not item_id or not isinstance(data, dict):
        raise ValueError("factory_binding_context_incomplete")
    return bind_scene_assets(batch_id=batch_id, item_id=item_id, data=data)
