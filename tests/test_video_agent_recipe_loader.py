import pytest

from agent.lab_runner.recipe_loader import RecipeValidationError, load_recipe, load_recipe_by_id


def test_three_recipes_load():
    assert load_recipe_by_id("structured-knowledge-video").id == "structured-knowledge-video"
    assert load_recipe_by_id("existing-assets-recut").id == "existing-assets-recut"
    assert load_recipe_by_id("book-summary-short").id == "book-summary-short"


def test_duplicate_step_id_rejected(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        "id: bad\nversion: 1\ndescription: bad\ninputContract: {required: [], optional: []}\nsteps:\n"
        "  - {id: a, kind: inspection, completionCondition: ok}\n"
        "  - {id: a, kind: inspection, completionCondition: ok}\n",
        encoding="utf-8",
    )
    with pytest.raises(RecipeValidationError, match="duplicate step id"):
        load_recipe(path)


def test_unknown_tool_rejected(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        "id: bad\nversion: 1\ndescription: bad\ninputContract: {required: [], optional: []}\nsteps:\n"
        "  - {id: a, kind: tool, tool: unknown_tool, completionCondition: ok}\n",
        encoding="utf-8",
    )
    with pytest.raises(RecipeValidationError, match="unknown tool"):
        load_recipe(path)


def test_unknown_policy_rejected(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        "id: bad\nversion: 1\ndescription: bad\ninputContract: {required: [], optional: []}\nsteps:\n"
        "  - {id: a, kind: approval, policy: unknown_policy, completionCondition: ok}\n",
        encoding="utf-8",
    )
    with pytest.raises(RecipeValidationError, match="unknown policy"):
        load_recipe(path)


def test_cycle_dependency_rejected(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        "id: bad\nversion: 1\ndescription: bad\ninputContract: {required: [], optional: []}\nsteps:\n"
        "  - {id: a, kind: inspection, inputFrom: [], completionCondition: ok}\n"
        "  - {id: b, kind: inspection, inputFrom: [a], completionCondition: ok}\n",
        encoding="utf-8",
    )
    recipe = load_recipe(path)
    assert [step.id for step in recipe.steps] == ["a", "b"]
