"""Resolver tests for the immutable Resolved Director Policy compiler."""
from __future__ import annotations

import pytest

from models.director_pack import DirectorPackManifest
from services import director_policy_resolver as resolver
from services import director_pack_store as store

LOCAL_ONLY = {"externalAllowed": False, "paidAllowed": False, "maxCostPerRun": 0}

MANIFEST = DirectorPackManifest.model_validate(
    {
        "format": "videoforge.director-pack",
        "formatVersion": 1,
        "id": "kvxw/knowledge-cinematic",
        "version": "1.0.0",
        "name": "Knowledge Cinematic",
        "publisher": {"id": "kvxw", "name": "KV"},
        "compatibility": {"directorProtocol": "1.x"},
        "routing": {
            "default": ["code_visual", "stickman"],
            "intents": {
                "causal": ["code_visual"],
                "data": ["code_visual"],
                "relationship": ["stickman", "code_visual"],
                "human_action": ["stickman"],
            },
        },
        "style": {"anchor": "warm low-saturation", "avoid": []},
        "rhythm": {"visualDensity": "balanced", "motionPreference": "static"},
        "continuity": {"scope": "project", "anchor": "stable palette"},
        "candidates": {"count": 2},
        "approval": {"defaultMode": "auto"},
        "durationPolicy": {"image": "hold_to_scene", "video": "crop"},
        "dependencies": {
            "providers": [
                {"id": "code_visual", "version": "1.x", "required": False},
                {"id": "stickman", "version": "1.x", "required": False},
            ],
            "skills": [],
        },
        "fallback": {
            "missingOptionalProvider": "continue",
            "missingRequiredProvider": "block",
            "providerFailure": "next_declared",
            "exhaustedProviders": "review",
        },
    }
)

STICKMAN_METADATA = {
    "providerId": "stickman",
    "version": "1.0.0",
    "trust": "TRUSTED_BUILTIN",
    "templateIds": [
        "stickman/inner_conflict",
        "stickman/escape_enclosure",
        "stickman/relationship_tug",
        "stickman/burden_boulder",
        "stickman/generic_two_person_relation",
    ],
}

CODE_VISUAL_METADATA = {
    "providerId": "code_visual",
    "version": "1.0.0",
    "trust": "TRUSTED_BUILTIN",
    "templateIds": [
        "code_visual/keyword",
        "code_visual/causal",
        "code_visual/process",
        "code_visual/comparison",
        "code_visual/ranking",
        "code_visual/topology",
    ],
}

ALL_PROVIDERS = [CODE_VISUAL_METADATA, STICKMAN_METADATA]


def test_resolve_degrades_optional_provider_but_never_invents_route(monkeypatch):
    monkeypatch.setattr(resolver, "list_providers", lambda: [STICKMAN_METADATA])
    policy = resolver.resolve(MANIFEST, run_mode="auto", authorization=LOCAL_ONLY)
    assert policy.status == "enabled_with_degradation"
    assert policy.effectiveRouting["relationship"] == ["stickman"]
    assert policy.effectiveRouting["data"] == []
    assert "provider_missing:code_visual" in policy.degradations
    assert policy.effectiveApproval.forceReview is True


def test_user_review_can_never_be_weakened_to_auto(monkeypatch):
    monkeypatch.setattr(resolver, "list_providers", lambda: ALL_PROVIDERS)
    policy = resolver.resolve(MANIFEST, run_mode="review", authorization=LOCAL_ONLY)
    assert policy.effectiveApproval.mode == "review"


def test_full_local_auto_without_warnings_stays_auto(monkeypatch):
    monkeypatch.setattr(resolver, "list_providers", lambda: ALL_PROVIDERS)
    policy = resolver.resolve(MANIFEST, run_mode="auto", authorization=LOCAL_ONLY)
    assert policy.status == "enabled"
    assert policy.effectiveApproval.mode == "auto"
    assert policy.effectiveApproval.forceReview is False
    assert policy.effectiveRouting["causal"] == ["code_visual"]
    assert policy.effectiveRouting["relationship"] == ["stickman", "code_visual"]


def test_required_provider_missing_blocks_everything(monkeypatch):
    required = MANIFEST.model_copy(deep=True)
    required.dependencies.providers[0].required = True
    monkeypatch.setattr(resolver, "list_providers", lambda: [STICKMAN_METADATA])
    policy = resolver.resolve(required, run_mode="auto", authorization=LOCAL_ONLY)
    assert policy.status == "blocked"
    assert "provider_missing:code_visual" in policy.degradations


def test_no_usable_route_at_all_blocks(monkeypatch):
    no_providers = MANIFEST.model_copy(deep=True)
    no_providers.routing.default = []
    no_providers.routing.intents = {"causal": ["missing_provider"]}
    monkeypatch.setattr(resolver, "list_providers", lambda: [])
    policy = resolver.resolve(no_providers, run_mode="auto", authorization=LOCAL_ONLY)
    assert policy.status == "blocked"


def test_unknown_template_id_is_degraded_but_route_survives(monkeypatch):
    data = MANIFEST.model_dump()
    data["templates"] = [
        {"id": "code_visual/nonexistent", "provider": "code_visual", "useFor": ["causal"]}
    ]
    manifest = DirectorPackManifest.model_validate(data)
    monkeypatch.setattr(resolver, "list_providers", lambda: ALL_PROVIDERS)
    policy = resolver.resolve(manifest, run_mode="auto", authorization=LOCAL_ONLY)
    assert "template_missing:code_visual/nonexistent" in policy.degradations
    assert policy.effectiveRouting["causal"] == ["code_visual"]


def test_missing_reference_file_is_degraded(tmp_path):
    data = MANIFEST.model_dump()
    data["references"] = [{"path": "references/guide.svg", "role": "composition"}]
    manifest = DirectorPackManifest.model_validate(data)
    # no installed_dir provided: existence check is skipped
    policy = resolver.resolve(manifest, run_mode="auto", authorization=LOCAL_ONLY)
    assert not any("reference_missing" in item for item in policy.degradations)
    # with installed_dir missing the file: degraded
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    policy2 = resolver.resolve(
        manifest, run_mode="auto", authorization=LOCAL_ONLY, installed_dir=empty_dir
    )
    assert "reference_missing:references/guide.svg" in policy2.degradations


def test_unverified_provider_forces_review(monkeypatch):
    untrusted = [{"providerId": "stickman", "version": "1.0.0", "trust": "UNVERIFIED", "templateIds": []}]
    monkeypatch.setattr(resolver, "list_providers", lambda: untrusted)
    policy = resolver.resolve(MANIFEST, run_mode="auto", authorization=LOCAL_ONLY)
    assert policy.effectiveApproval.forceReview is True
    assert policy.effectiveApproval.mode == "review"


def test_resolve_installed_roundtrip_builtin_pack(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DIRECTOR_PACKS_DIR", tmp_path / "installed")
    record = store.install_builtin("kvxw/knowledge-cinematic", "1.0.0")
    policy = resolver.resolve_installed(
        record["id"], record["version"], run_mode="auto", authorization=LOCAL_ONLY
    )
    assert policy.pack.id == "kvxw/knowledge-cinematic"
    assert policy.pack.manifestDigest.startswith("sha256:")
    assert policy.pack.sourceTrust == "TRUSTED_BUILTIN"
    assert policy.effectiveRouting["causal"][0] == "code_visual"
    assert policy.effectiveRouting["relationship"][0] == "stickman"
    roles = {item.role for item in policy.effectiveReferences}
    assert roles == {"composition", "positive_example", "negative_example", "palette"}


def test_resolve_installed_missing_pack_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DIRECTOR_PACKS_DIR", tmp_path / "installed")
    with pytest.raises(store.DirectorPackStoreError) as exc:
        resolver.resolve_installed("kvxw/knowledge-cinematic", "9.9.9", "auto", LOCAL_ONLY)
    assert exc.value.code == "pack_not_installed"
