"""Bind product recipes to the existing Lab tool contract without duplicating it."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agent.lab_runner.recipe_loader import RecipeValidationError, load_recipe_by_id
from agent.lab_runner.tool_registry import TOOL_SPECS, ToolSpec


@dataclass(frozen=True)
class RecipeBinding:
    recipe_id: str
    recipe_version: int
    required_inputs: tuple[str, ...]
    optional_inputs: tuple[str, ...]
    steps: tuple[dict[str, Any], ...]
    capabilities: tuple[dict[str, Any], ...]


class CapabilityRegistry:
    """Read-only projection of the Lab's recipes and tool specs for an LLM."""

    def __init__(self, recipes_root: str | Path | None = None):
        self.recipes_root = Path(recipes_root) if recipes_root else Path(__file__).parents[1] / "recipes"

    def recipe_ids(self) -> list[str]:
        return sorted(path.stem for path in self.recipes_root.glob("*.yaml"))

    def bind_recipe(self, recipe_id: str) -> RecipeBinding:
        recipe = load_recipe_by_id(recipe_id, self.recipes_root)
        required = tuple(str(item) for item in recipe.inputContract.get("required", []))
        optional = tuple(str(item) for item in recipe.inputContract.get("optional", []))
        steps: list[dict[str, Any]] = []
        capabilities: dict[str, dict[str, Any]] = {}
        for step in recipe.steps:
            steps.append({
                "id": step.id,
                "kind": step.kind,
                "tool": step.tool,
                "completionCondition": step.completionCondition,
                "dependsOn": list(step.inputFrom),
                "approvalPolicy": step.policy,
                "onError": step.onError,
                "auto": step.auto,
            })
            if step.tool:
                capabilities[step.tool] = self._capability_view(TOOL_SPECS[step.tool])
        return RecipeBinding(
            recipe_id=recipe.id,
            recipe_version=recipe.version,
            required_inputs=required,
            optional_inputs=optional,
            steps=tuple(steps),
            capabilities=tuple(capabilities[name] for name in sorted(capabilities)),
        )

    def available_inputs(self, binding: RecipeBinding, context: dict[str, Any]) -> dict[str, list[str]]:
        """Return only recipe-contract gaps; aliases keep recipe YAML backwards compatible."""
        project = context.get("project") or {}
        has_project = bool(project.get("id"))
        has_script = bool(project.get("script")) or bool(context.get("subtitleTimeline", {}).get("count"))
        has_assets = bool((context.get("assetCoverage") or {}).get("totalAssets"))
        supplied = set(context.get("inputKeys") or [])
        if has_project:
            supplied.update({"project_id", "projectId", "source_script_or_project_id"})
        if has_script:
            supplied.update({"source_script_or_project_id", "audio_or_subtitles"})
        if has_assets:
            supplied.add("existing_assets")
        return {
            "available": sorted(supplied),
            "missingRequired": sorted(item for item in binding.required_inputs if item not in supplied),
        }

    @staticmethod
    def _capability_view(spec: ToolSpec) -> dict[str, Any]:
        view = asdict(spec)
        return {
            "name": view["name"],
            "mode": view["mode"],
            "risk": view["risk"],
            "idempotent": view["idempotent"],
            "approvalPolicy": view["requiredPolicy"],
            "allowedStates": view["allowedStates"],
            "produces": view["produces"],
            "knownErrors": view["errors"],
        }


__all__ = ["CapabilityRegistry", "RecipeBinding", "RecipeValidationError"]
