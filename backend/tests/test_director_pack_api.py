"""HTTP API tests for the Director Pack protocol v1."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import create_app
from services import director_pack_store as store

MANIFEST = """\
format: videoforge.director-pack
formatVersion: 1
id: kvxw/knowledge-cinematic
version: 1.0.0
name: Knowledge Cinematic
publisher:
  id: kvxw
  name: KV
compatibility:
  directorProtocol: 1.x
routing:
  default: [code_visual, stickman]
  intents:
    causal: [code_visual]
    relationship: [stickman]
style:
  anchor: warm low-saturation
  avoid: [random style shifts]
rhythm:
  visualDensity: balanced
  motionPreference: static
continuity:
  scope: project
  anchor: stable palette
candidates:
  count: 2
approval:
  defaultMode: auto
durationPolicy:
  image: hold_to_scene
  video: crop
dependencies:
  providers:
    - {id: code_visual, version: 1.x, required: false}
    - {id: stickman, version: 1.x, required: false}
  skills: []
fallback:
  missingOptionalProvider: continue
  missingRequiredProvider: block
  providerFailure: next_declared
  exhaustedProviders: review
editable: [style.anchor, rhythm.visualDensity, candidates.count, approval.defaultMode]
references:
  - path: references/guide.svg
    role: composition
"""


def build_pack(path: Path, *, manifest: str = MANIFEST, extra: dict[str, bytes] | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("director-pack.yaml", manifest)
        zf.writestr("references/guide.svg", "<svg></svg>")
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return path


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DIRECTOR_PACKS_DIR", tmp_path / "director-packs")
    return TestClient(create_app())


@pytest.fixture
def pack_file(tmp_path) -> Path:
    return build_pack(tmp_path / "pack.vfdirector")


def _upload(client, pack: Path):
    return client.post(
        "/api/director-packs/import",
        files={"file": ("pack.vfdirector", pack.read_bytes(), "application/zip")},
    )


def test_import_list_get_resolve_export_derive_and_lifecycle(client, pack_file):
    # import → installation record with digests
    imported = _upload(client, pack_file)
    assert imported.status_code == 200
    record = imported.json()
    assert record["id"] == "kvxw/knowledge-cinematic"
    assert record["version"] == "1.0.0"
    assert record["manifestDigest"].startswith("sha256:")
    assert record["archiveDigest"].startswith("sha256:")
    assert record["sourceTrust"] == "LOCAL"
    assert record["status"] == "enabled"
    assert record["degradations"] == []

    # list → contains the pack id
    listed = client.get("/api/director-packs")
    assert listed.status_code == 200
    assert [pack["id"] for pack in listed.json()] == ["kvxw/knowledge-cinematic"]
    assert listed.json()[0]["name"] == "Knowledge Cinematic"
    assert listed.json()[0]["referenceCount"] == 1

    # get → detail with parsed manifest
    detail = client.get("/api/director-packs/kvxw/knowledge-cinematic/1.0.0")
    assert detail.status_code == 200
    assert detail.json()["manifest"]["id"] == "kvxw/knowledge-cinematic"

    # resolve auto → frozen policy with sha256 manifestDigest
    resolved = client.post(
        "/api/director-packs/kvxw/knowledge-cinematic/1.0.0/resolve",
        json={"runMode": "auto"},
    )
    assert resolved.status_code == 200
    policy = resolved.json()
    assert policy["pack"]["manifestDigest"].startswith("sha256:")
    assert policy["pack"]["manifestDigest"] == record["manifestDigest"]
    assert policy["effectiveRouting"]["causal"] == ["code_visual"]
    assert policy["effectiveRouting"]["relationship"] == ["stickman"]
    assert policy["effectiveApproval"]["mode"] == "auto"
    assert policy["status"] == "enabled"

    # resolve review can never be weakened to auto
    review = client.post(
        "/api/director-packs/kvxw/knowledge-cinematic/1.0.0/resolve",
        json={"runMode": "review"},
    )
    assert review.status_code == 200
    assert review.json()["effectiveApproval"]["mode"] == "review"

    # export → zip magic bytes
    exported = client.get("/api/director-packs/kvxw/knowledge-cinematic/1.0.0/export")
    assert exported.status_code == 200
    assert exported.content[:2] == b"PK"
    assert "knowledge-cinematic-1.0.0.vfdirector" in exported.headers.get("content-disposition", "")

    # derive → new id, editable field applied, derivedFrom recorded
    derived = client.post(
        "/api/director-packs/kvxw/knowledge-cinematic/1.0.0/derive",
        json={
            "id": "kvxw/knowledge-cinematic-custom",
            "version": "1.0.0",
            "style": {"anchor": "cool palette"},
        },
    )
    assert derived.status_code == 200
    manifest = derived.json()
    assert manifest["id"] == "kvxw/knowledge-cinematic-custom"
    assert manifest["style"]["anchor"] == "cool palette"
    assert manifest["derivedFrom"] == {"id": "kvxw/knowledge-cinematic", "version": "1.0.0"}
    assert any(pack["id"] == manifest["id"] for pack in client.get("/api/director-packs").json())

    asset = client.get(
        "/api/director-packs/kvxw/knowledge-cinematic/1.0.0/assets/references/guide.svg"
    )
    assert asset.status_code == 200
    assert asset.headers["content-type"].startswith("image/svg+xml")

    # disable → enable
    disabled = client.post("/api/director-packs/kvxw/knowledge-cinematic/1.0.0/disable")
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    enabled = client.post("/api/director-packs/kvxw/knowledge-cinematic/1.0.0/enable")
    assert enabled.status_code == 200
    assert enabled.json()["status"] == "enabled"

    # delete → ok, then get → 404 pack_not_installed
    deleted = client.delete("/api/director-packs/kvxw/knowledge-cinematic/1.0.0")
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}
    gone = client.get("/api/director-packs/kvxw/knowledge-cinematic/1.0.0")
    assert gone.status_code == 404
    assert gone.json()["detail"]["code"] == "pack_not_installed"
    # no local absolute path is leaked into the error body
    assert str(pack_file.parent) not in gone.json()["detail"]["message"]


def test_reimport_same_identity_different_digest_is_409(client, tmp_path):
    first = _upload(client, build_pack(tmp_path / "first.vfdirector"))
    assert first.status_code == 200
    changed = build_pack(
        tmp_path / "changed.vfdirector",
        manifest=MANIFEST.replace("warm low-saturation", "warm muted cinematic"),
    )
    second = _upload(client, changed)
    assert second.status_code == 409
    body = second.json()
    assert body["detail"]["code"] == "immutable_version_conflict"
    assert str(tmp_path) not in body["detail"]["message"]


def test_resolve_missing_pack_is_404(client):
    response = client.post(
        "/api/director-packs/nobody/nopack/9.9.9/resolve",
        json={"runMode": "auto"},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "pack_not_installed"


def test_resolve_rejects_unknown_run_mode(client, pack_file):
    assert _upload(client, pack_file).status_code == 200
    response = client.post(
        "/api/director-packs/kvxw/knowledge-cinematic/1.0.0/resolve",
        json={"runMode": "turbo"},
    )
    assert response.status_code == 422


def test_import_rejects_executable_member(client, tmp_path):
    evil = build_pack(tmp_path / "evil.vfdirector", extra={"evil.py": b"print('owned')"})
    response = _upload(client, evil)
    assert response.status_code == 422
    body = response.json()
    assert body["detail"]["code"] == "executable_payload"
    assert "evil.py" in body["detail"]["message"]


def test_derive_rejects_non_editable_field_is_422(client, pack_file):
    assert _upload(client, pack_file).status_code == 200
    response = client.post(
        "/api/director-packs/kvxw/knowledge-cinematic/1.0.0/derive",
        json={
            "id": "kvxw/knowledge-cinematic-custom",
            "version": "1.0.0",
            "routing": {"default": ["stickman"]},
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "derive_field_not_editable"


def test_derive_rejects_other_publisher_is_409(client, pack_file):
    assert _upload(client, pack_file).status_code == 200
    response = client.post(
        "/api/director-packs/kvxw/knowledge-cinematic/1.0.0/derive",
        json={"id": "other/knowledge-cinematic", "version": "1.0.0"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "derive_requires_same_publisher"
