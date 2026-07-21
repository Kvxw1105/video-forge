import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.project import Project
from shared.structured_content import compile_structured_variant


def _structured_project():
    blocks = [
        {"id": "hook_01", "type": "HOOK", "text": "Hook"},
        {"id": "cta_01", "type": "CTA_TAG", "text": "CTA"},
        {"id": "bridge_in_01", "type": "BRIDGE_IN", "text": "Bridge in"},
        {"id": "story_01", "type": "STORY", "text": "Story"},
        {"id": "mechanism_01", "type": "MECHANISM", "text": "Mechanism"},
        {"id": "judgment_01", "type": "JUDGMENT", "text": "Judgment"},
        {"id": "short_outro_01", "type": "SHORT_OUTRO", "text": "Outro"},
        {"id": "bridge_out_01", "type": "BRIDGE_OUT", "text": "Bridge out"},
    ]
    variants = [
        {"id": "publish", "name": "Publish", "blockIds": ["hook_01", "cta_01", "story_01", "mechanism_01", "judgment_01", "short_outro_01"]},
        {"id": "master", "name": "Master", "blockIds": ["story_01", "mechanism_01", "judgment_01"]},
        {"id": "chapter", "name": "Chapter", "blockIds": ["bridge_in_01", "story_01", "mechanism_01", "judgment_01", "bridge_out_01"]},
    ]
    return {
        "id": "proj_structured",
        "script": "legacy script",
        "structuredContent": {
            "schemaVersion": 1,
            "episode": {
                "episodeId": "episode_001",
                "title": "Episode",
                "blocks": blocks,
                "variants": variants,
                "activeVariantId": "publish",
            },
        },
    }


def test_legacy_project_has_none_structured_content():
    assert Project().structuredContent is None


def test_structured_project_round_trips():
    project = Project.model_validate(_structured_project())
    restored = Project.model_validate(project.model_dump())
    assert restored.structuredContent == project.structuredContent


@pytest.mark.parametrize("payload", [
    {"schemaVersion": 2, "episode": {}},
    {"schemaVersion": "1", "episode": {}},
])
def test_schema_version_must_be_one(payload):
    with pytest.raises(ValueError):
        Project.model_validate({"structuredContent": payload})


def test_unknown_structured_field_is_rejected():
    payload = _structured_project()
    payload["structuredContent"]["unexpected"] = True
    with pytest.raises(ValueError):
        Project.model_validate(payload)


def test_invalid_block_type_is_rejected():
    payload = _structured_project()
    payload["structuredContent"]["episode"]["blocks"][0]["type"] = "NOT_A_BLOCK"
    with pytest.raises(ValueError):
        Project.model_validate(payload)


def test_duplicate_block_id_is_rejected():
    payload = _structured_project()
    payload["structuredContent"]["episode"]["blocks"][1]["id"] = "hook_01"
    with pytest.raises(ValueError):
        Project.model_validate(payload)


def test_duplicate_variant_id_is_rejected():
    payload = _structured_project()
    payload["structuredContent"]["episode"]["variants"][1]["id"] = "publish"
    with pytest.raises(ValueError):
        Project.model_validate(payload)


def test_duplicate_variant_block_reference_is_rejected():
    payload = _structured_project()
    payload["structuredContent"]["episode"]["variants"][0]["blockIds"] = ["hook_01", "hook_01"]
    with pytest.raises(ValueError):
        Project.model_validate(payload)


def test_missing_block_reference_is_rejected():
    payload = _structured_project()
    payload["structuredContent"]["episode"]["variants"][0]["blockIds"] = ["missing"]
    with pytest.raises(ValueError):
        Project.model_validate(payload)


def test_missing_active_variant_is_rejected():
    payload = _structured_project()
    payload["structuredContent"]["episode"]["activeVariantId"] = "missing"
    with pytest.raises(ValueError):
        Project.model_validate(payload)


def test_active_variant_is_required_when_variants_exist():
    payload = _structured_project()
    payload["structuredContent"]["episode"]["activeVariantId"] = None
    with pytest.raises(ValueError):
        Project.model_validate(payload)


def test_unsafe_ids_are_rejected():
    payload = _structured_project()
    payload["structuredContent"]["episode"]["blocks"][0]["id"] = "../escape"
    with pytest.raises(ValueError):
        Project.model_validate(payload)


def test_revision_must_be_at_least_one():
    payload = _structured_project()
    payload["structuredContent"]["episode"]["blocks"][0]["revision"] = 0
    with pytest.raises(ValueError):
        Project.model_validate(payload)


def test_all_supported_block_types_are_accepted():
    payload = _structured_project()
    types = ["HOOK", "CTA_TAG", "PROBLEM", "STORY", "MECHANISM", "JUDGMENT", "METHOD", "SHORT_OUTRO", "BRIDGE_IN", "BRIDGE_OUT", "COMMENT_CTA"]
    payload["structuredContent"]["episode"]["blocks"] = [
        {"id": f"block_{index}", "type": block_type, "text": block_type}
        for index, block_type in enumerate(types)
    ]
    payload["structuredContent"]["episode"]["variants"] = []
    payload["structuredContent"]["episode"]["activeVariantId"] = None
    assert len(Project.model_validate(payload).structuredContent.episode.blocks) == len(types)


def test_episode_can_be_saved_as_variant_draft_without_active_variant():
    payload = _structured_project()
    payload["structuredContent"]["episode"]["variants"] = []
    payload["structuredContent"]["episode"]["activeVariantId"] = None
    assert Project.model_validate(payload).structuredContent.episode.activeVariantId is None


def test_empty_text_is_allowed_at_model_boundary():
    payload = _structured_project()
    payload["structuredContent"]["episode"]["blocks"][0]["text"] = ""
    project = Project.model_validate(payload)
    assert project.structuredContent.episode.blocks[0].text == ""


def test_metadata_is_preserved_without_interpretation():
    payload = _structured_project()
    payload["structuredContent"]["episode"]["blocks"][0]["metadata"] = {"source": "draft", "score": 0.5}
    project = Project.model_validate(payload)
    result = compile_structured_variant(project, "publish")
    assert result.project_view["structuredContent"]["episode"]["blocks"][0]["metadata"] == {"source": "draft", "score": 0.5}


@pytest.mark.parametrize("variant_id, expected", [
    ("publish", ("hook_01", "cta_01", "story_01", "mechanism_01", "judgment_01", "short_outro_01")),
    ("master", ("story_01", "mechanism_01", "judgment_01")),
    ("chapter", ("bridge_in_01", "story_01", "mechanism_01", "judgment_01", "bridge_out_01")),
])
def test_variant_order_and_script(variant_id, expected):
    result = compile_structured_variant(Project.model_validate(_structured_project()), variant_id)
    assert result.block_ids == expected
    assert result.script == "\n\n".join(block.text for block in result.blocks)


def test_disabled_and_empty_blocks_are_skipped_with_warnings():
    payload = _structured_project()
    blocks = payload["structuredContent"]["episode"]["blocks"]
    blocks[0]["enabled"] = False
    blocks[1]["text"] = "   "
    result = compile_structured_variant(Project.model_validate(payload), "publish")
    assert result.block_ids == ("story_01", "mechanism_01", "judgment_01", "short_outro_01")
    assert len(result.warnings) == 2


def test_compiler_does_not_mutate_input_and_is_deterministic():
    payload = _structured_project()
    before = copy.deepcopy(payload)
    project = Project.model_validate(payload)
    first = compile_structured_variant(project, "publish")
    second = compile_structured_variant(project, "publish")
    assert payload == before
    assert first == second
    assert first.project_view is not project


def test_variants_do_not_share_mutable_project_views():
    project = Project.model_validate(_structured_project())
    publish = compile_structured_variant(project, "publish")
    master = compile_structured_variant(project, "master")
    publish.project_view["script"] = "changed"
    assert master.project_view["script"] != "changed"


def test_unknown_variant_is_controlled_error():
    with pytest.raises(KeyError):
        compile_structured_variant(Project.model_validate(_structured_project()), "missing")


def test_legacy_project_is_controlled_error():
    with pytest.raises(ValueError, match="not a structured project"):
        compile_structured_variant(Project(), "publish")


def test_project_view_keeps_media_fields_and_sets_only_derived_script():
    payload = _structured_project()
    payload["assets"] = [{"id": "asset_1", "type": "image", "name": "a", "path": "a.png"}]
    payload["segments"] = [{"id": "seg_1", "assetPath": "a.png", "type": "image"}]
    project = Project.model_validate(payload)
    result = compile_structured_variant(project, "master")
    assert result.project_view["assets"] == project.model_dump()["assets"]
    assert result.project_view["segments"] == project.model_dump()["segments"]
    assert result.project_view["structuredContent"]["episode"]["activeVariantId"] == "master"
