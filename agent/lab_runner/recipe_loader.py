from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import Recipe, RecipeStep
from .policy_checker import AUTO_ALLOW, APPROVAL_REQUIRED, DENY
from .tool_registry import TOOL_SPECS


ALLOWED_KINDS = {"tool", "approval", "wait", "inspection", "evaluation"}
KNOWN_POLICIES = set(AUTO_ALLOW) | set(APPROVAL_REQUIRED) | set(DENY) | {"script_content_change", "analyze_script"}


class RecipeValidationError(ValueError):
    pass


def _check_cycle(steps: list[RecipeStep]) -> None:
    by_id = {step.id: step for step in steps}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visited:
            return
        if step_id in visiting:
            raise RecipeValidationError("cycle dependency detected")
        visiting.add(step_id)
        for parent in by_id[step_id].inputFrom:
            visit(parent)
        visiting.remove(step_id)
        visited.add(step_id)

    for step in steps:
        visit(step.id)


def load_recipe(path: str | Path) -> Recipe:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    steps_raw = raw.get("steps") or []
    seen: set[str] = set()
    steps: list[RecipeStep] = []
    for item in steps_raw:
        step_id = item.get("id")
        if not step_id:
            raise RecipeValidationError("step missing id")
        if step_id in seen:
            raise RecipeValidationError(f"duplicate step id: {step_id}")
        seen.add(step_id)
        kind = item.get("kind") or item.get("type")
        if kind == "external_wait":
            kind = "wait"
        if kind == "agent":
            kind = "inspection"
        if kind not in ALLOWED_KINDS:
            raise RecipeValidationError(f"unknown step kind: {kind}")
        tool = item.get("tool")
        if tool and tool not in TOOL_SPECS:
            raise RecipeValidationError(f"unknown tool: {tool}")
        policy = item.get("policy")
        if policy and policy not in KNOWN_POLICIES:
            raise RecipeValidationError(f"unknown policy: {policy}")
        completion = item.get("completionCondition")
        if not completion:
            raise RecipeValidationError(f"missing completionCondition: {step_id}")
        input_from = list(item.get("inputFrom") or [])
        for parent in input_from:
            if parent not in seen:
                raise RecipeValidationError(f"invalid inputFrom for {step_id}: {parent}")
        steps.append(
            RecipeStep(
                id=step_id,
                kind=kind,
                tool=tool,
                policy=policy,
                required=bool(item.get("required", True)),
                inputFrom=input_from,
                produces=list(item.get("produces") or item.get("outputs") or []),
                completionCondition=completion,
                retry=item.get("retry"),
                onError=item.get("onError", "fail"),
                auto=bool(item.get("auto", True)),
                condition=item.get("condition") or item.get("resume_when"),
            )
        )
    required_ids = {step.id for step in steps if step.required}
    reachable = set()
    for step in steps:
        if not step.inputFrom:
            reachable.add(step.id)
        elif set(step.inputFrom).issubset(reachable):
            reachable.add(step.id)
    unreachable = required_ids - reachable
    if unreachable:
        raise RecipeValidationError(f"unreachable required steps: {sorted(unreachable)}")
    _check_cycle(steps)
    return Recipe(
        id=raw["id"],
        version=int(raw.get("version") or 1),
        description=str(raw.get("description") or ""),
        inputContract=raw.get("inputContract") or {"required": raw.get("required_inputs") or [], "optional": []},
        steps=steps,
    )


def load_recipe_by_id(recipe_id: str, root: str | Path = "agent/recipes") -> Recipe:
    path = Path(root) / f"{recipe_id}.yaml"
    if not path.exists():
        raise RecipeValidationError(f"recipe not found: {recipe_id}")
    return load_recipe(path)
