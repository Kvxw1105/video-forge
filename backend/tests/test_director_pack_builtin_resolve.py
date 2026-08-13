"""Built-in pack resolution tests (Task 4 dependency).

``resolve_installed`` lives in ``services/director_policy_resolver`` which is
developed in parallel (Task 4) and is not yet merged into this branch. The
import is deliberately inside the test body so collection succeeds; until the
resolver lands, this test fails with ModuleNotFoundError. Once Task 4 merges,
this test must pass unchanged.
"""
from __future__ import annotations

import pytest

from services import director_pack_store as store

LOCAL_ONLY_AUTHORIZATION = {"externalAllowed": False, "paidAllowed": False, "maxCostPerRun": 0}


def test_builtin_knowledge_pack_has_real_references_and_mixed_routes(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DIRECTOR_PACKS_DIR", tmp_path / "installed")
    record = store.install_builtin("kvxw/knowledge-cinematic", "1.0.0")

    from services.director_policy_resolver import resolve_installed

    policy = resolve_installed(
        record["id"], record["version"], run_mode="auto", authorization=LOCAL_ONLY_AUTHORIZATION
    )
    assert policy.effectiveRouting["causal"][0] == "code_visual"
    assert policy.effectiveRouting["relationship"][0] == "stickman"
    assert {item.role for item in policy.effectiveReferences} == {
        "composition",
        "positive_example",
        "negative_example",
        "palette",
    }
    again = resolve_installed(
        record["id"], record["version"], run_mode="auto", authorization=LOCAL_ONLY_AUTHORIZATION
    )
    assert policy.policyDigest.startswith("sha256:")
    assert again.policyDigest == policy.policyDigest
