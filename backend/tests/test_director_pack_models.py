"""Strict data-only model tests for Director Pack protocol v1."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.director_pack import DirectorPackManifest


def minimal_manifest() -> dict:
    return {
        "format": "videoforge.director-pack",
        "formatVersion": 1,
        "id": "kvxw/knowledge-cinematic",
        "version": "1.0.0",
        "name": "Knowledge Cinematic",
        "publisher": {"id": "kvxw", "name": "KV"},
        "compatibility": {"directorProtocol": "1.x"},
        "routing": {"default": ["code_visual"], "intents": {"causal": ["code_visual"]}},
        "style": {"anchor": "warm low-saturation", "avoid": []},
        "rhythm": {"visualDensity": "balanced", "motionPreference": "static"},
        "continuity": {"scope": "project", "anchor": "stable palette"},
        "candidates": {"count": 2},
        "approval": {"defaultMode": "auto"},
        "durationPolicy": {"image": "hold_to_scene", "video": "crop"},
        "dependencies": {"providers": [], "skills": []},
        "fallback": {
            "missingOptionalProvider": "continue",
            "missingRequiredProvider": "block",
            "providerFailure": "next_declared",
            "exhaustedProviders": "review",
        },
    }


def test_manifest_is_strict_and_data_only():
    manifest = DirectorPackManifest.model_validate(minimal_manifest())
    assert manifest.format == "videoforge.director-pack"
    assert manifest.routing.intents["causal"] == ["code_visual"]
    invalid = minimal_manifest() | {"installScript": "python setup.py"}
    try:
        DirectorPackManifest.model_validate(invalid)
    except ValidationError as exc:
        assert "installScript" in str(exc)
    else:
        raise AssertionError("unknown executable field must be rejected")


def test_unknown_top_level_field_is_rejected():
    invalid = minimal_manifest() | {"onRender": "render.py"}
    with pytest.raises(ValidationError) as exc:
        DirectorPackManifest.model_validate(invalid)
    assert "onRender" in str(exc.value)


def test_executable_like_nested_fields_are_rejected():
    invalid = minimal_manifest()
    invalid["style"] = {"anchor": "warm", "avoid": [], "dynamicFilter": "lambda x: x"}
    with pytest.raises(ValidationError) as exc:
        DirectorPackManifest.model_validate(invalid)
    assert "dynamicFilter" in str(exc.value)


def test_format_and_format_version_are_locked():
    invalid = minimal_manifest() | {"format": "videoforge.director-pack-v2"}
    with pytest.raises(ValidationError):
        DirectorPackManifest.model_validate(invalid)
    invalid2 = minimal_manifest() | {"formatVersion": 2}
    with pytest.raises(ValidationError):
        DirectorPackManifest.model_validate(invalid2)


@pytest.mark.parametrize(
    "pack_id",
    ["KV/Knowledge", "kvxw/knowledge cinematic", "kvxw/", "/knowledge", "a" * 65 + "/x", "kvxw/" + "b" * 65],
)
def test_pack_id_must_match_publisher_slug(pack_id):
    invalid = minimal_manifest() | {"id": pack_id}
    with pytest.raises(ValidationError):
        DirectorPackManifest.model_validate(invalid)


@pytest.mark.parametrize("version", ["1", "1.0", "v1.0.0", "1.0.0.0", "1..0", "1.0.0 "])
def test_version_must_be_semver(version):
    invalid = minimal_manifest() | {"version": version}
    with pytest.raises(ValidationError):
        DirectorPackManifest.model_validate(invalid)


def test_intent_keys_must_come_from_shared_enum():
    invalid = minimal_manifest()
    invalid["routing"]["intents"] = {"not_an_intent": ["code_visual"]}
    with pytest.raises(ValidationError) as exc:
        DirectorPackManifest.model_validate(invalid)
    assert "not_an_intent" in str(exc.value)


def test_skill_dependency_is_advisory_only():
    manifest = minimal_manifest()
    manifest["dependencies"]["skills"] = [{"id": "some-skill", "version": "1.0.0", "role": "advisory"}]
    DirectorPackManifest.model_validate(manifest)
    manifest["dependencies"]["skills"] = [
        {"id": "some-skill", "version": "1.0.0", "role": "advisory", "required": True}
    ]
    with pytest.raises(ValidationError):
        DirectorPackManifest.model_validate(manifest)


def test_candidate_count_is_restricted():
    manifest = minimal_manifest()
    manifest["candidates"]["count"] = 4
    DirectorPackManifest.model_validate(manifest)
    manifest["candidates"]["count"] = 3
    with pytest.raises(ValidationError):
        DirectorPackManifest.model_validate(manifest)


def test_duration_policy_is_restricted():
    manifest = minimal_manifest()
    manifest["durationPolicy"] = {"image": "hold_to_scene", "video": "crop"}
    DirectorPackManifest.model_validate(manifest)
    manifest["durationPolicy"] = {"image": "shuffle", "video": "crop"}
    with pytest.raises(ValidationError):
        DirectorPackManifest.model_validate(manifest)


def test_missing_required_sections_are_rejected():
    missing = minimal_manifest()
    del missing["routing"]
    with pytest.raises(ValidationError):
        DirectorPackManifest.model_validate(missing)


def test_templates_and_references_cap_at_max_lengths():
    manifest = minimal_manifest()
    manifest["references"] = [{"path": f"references/r{i}.svg", "role": "guide"} for i in range(101)]
    with pytest.raises(ValidationError):
        DirectorPackManifest.model_validate(manifest)


def test_derived_from_tracks_pack_identity():
    manifest = minimal_manifest()
    manifest["derivedFrom"] = {"id": "kvxw/knowledge-cinematic", "version": "1.0.0"}
    parsed = DirectorPackManifest.model_validate(manifest)
    assert parsed.derivedFrom.id == "kvxw/knowledge-cinematic"
    assert parsed.derivedFrom.version == "1.0.0"
