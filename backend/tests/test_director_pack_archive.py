"""Safety and lifecycle tests for Director Pack archive + store."""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from services import director_pack_archive as archive
from services import director_pack_store as store

VALID_MANIFEST = """\
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


def make_pack(tmp_path: Path, *, manifest: str | None = None, extra_entries: dict[str, bytes] | None = None) -> Path:
    archive_path = Path(tmp_path) / "pack.vfdirector"
    Path(tmp_path).mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("director-pack.yaml", manifest or VALID_MANIFEST)
        zf.writestr("references/guide.svg", "<svg xmlns='http://www.w3.org/2000/svg'></svg>")
        for name, data in (extra_entries or {}).items():
            zf.writestr(name, data)
    return archive_path


def test_archive_rejects_executable_and_parent_path(tmp_path):
    bad = tmp_path / "bad.vfdirector"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("director-pack.yaml", VALID_MANIFEST)
        zf.writestr("../renderer.py", "print('owned')")
    with pytest.raises(archive.DirectorPackArchiveError) as exc:
        archive.inspect_archive(bad)
    assert exc.value.code in {"unsafe_path", "executable_payload"}


def test_archive_rejects_absolute_and_windows_drive_paths(tmp_path):
    for entry in ("C:/evil.py", "/etc/passwd", "references/../../evil.py"):
        bad = tmp_path / "bad.vfdirector"
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("director-pack.yaml", VALID_MANIFEST)
            zf.writestr(entry, "x")
        with pytest.raises(archive.DirectorPackArchiveError) as exc:
            archive.inspect_archive(bad)
        assert exc.value.code == "unsafe_path"


def test_archive_rejects_unknown_or_dangerous_extensions(tmp_path):
    for entry in ("hook.js", "presets/evil.sh", "install.bat", "run.py"):
        bad = tmp_path / "bad.vfdirector"
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("director-pack.yaml", VALID_MANIFEST)
            zf.writestr(entry, "x")
        with pytest.raises(archive.DirectorPackArchiveError) as exc:
            archive.inspect_archive(bad)
        assert exc.value.code == "executable_payload"


def test_archive_rejects_symlink_and_duplicate_normalized_paths(tmp_path):
    import zipfile as zf_mod

    bad = tmp_path / "symlink.vfdirector"
    with zf_mod.ZipFile(bad, "w") as zf:
        zf.writestr("director-pack.yaml", VALID_MANIFEST)
        info = zf_mod.ZipInfo("references/link.svg")
        info.create_system = 3
        info.external_attr = (0o120777 << 16)
        zf.writestr(info, "")
    with pytest.raises(archive.DirectorPackArchiveError) as exc:
        archive.inspect_archive(bad)
    assert exc.value.code == "unsafe_symlink"

    dup = tmp_path / "dup.vfdirector"
    with zf_mod.ZipFile(dup, "w") as zf:
        zf.writestr("director-pack.yaml", VALID_MANIFEST)
        zf.writestr("presets/palette.yaml", "a: 1")
        zf.writestr("presets/./palette.yaml", "a: 1")
    with pytest.raises(archive.DirectorPackArchiveError) as exc:
        archive.inspect_archive(dup)
    assert exc.value.code == "duplicate_path"


def test_archive_missing_entrypoint_or_non_mapping_yaml(tmp_path):
    bad = tmp_path / "missing.vfdirector"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("other.yaml", "x: 1")
    with pytest.raises(archive.DirectorPackArchiveError) as exc:
        archive.inspect_archive(bad)
    assert exc.value.code == "missing_entrypoint"

    bad2 = tmp_path / "bad_yaml.vfdirector"
    with zipfile.ZipFile(bad2, "w") as zf:
        zf.writestr("director-pack.yaml", "- just a list")
    with pytest.raises(archive.DirectorPackArchiveError) as exc:
        archive.inspect_archive(bad2)
    assert exc.value.code == "entrypoint_not_mapping"


def test_archive_computes_digests(tmp_path):
    pack = make_pack(tmp_path)
    inspected = archive.inspect_archive(pack)
    assert inspected.manifest_digest.startswith("sha256:")
    assert inspected.archive_digest.startswith("sha256:")
    assert len(inspected.manifest_digest.split(":", 1)[1]) == 64
    assert inspected.manifest["id"] == "kvxw/knowledge-cinematic"


def test_same_id_version_cannot_change_digest(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DIRECTOR_PACKS_DIR", tmp_path / "installed")
    first = store.install(make_pack(tmp_path))
    assert first["status"] == "enabled"
    second_pack = make_pack(
        tmp_path / "v2",
        manifest=VALID_MANIFEST.replace("warm low-saturation", "warm muted cinematic"),
    )
    with pytest.raises(store.DirectorPackStoreError) as exc:
        store.install(second_pack)
    assert exc.value.code == "immutable_version_conflict"


def test_reinstall_same_digest_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DIRECTOR_PACKS_DIR", tmp_path / "installed")
    pack = make_pack(tmp_path)
    first = store.install(pack)
    second = store.install(pack)
    assert first["status"] == "enabled"
    assert second["status"] == "enabled"


def test_list_and_read_installed_pack(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DIRECTOR_PACKS_DIR", tmp_path / "installed")
    store.install(make_pack(tmp_path))
    packs = store.list_packs()
    assert len(packs) == 1
    assert packs[0]["id"] == "kvxw/knowledge-cinematic"
    detail = store.get_pack("kvxw/knowledge-cinematic", "1.0.0")
    assert detail["version"] == "1.0.0"
    assert detail["status"] == "enabled"


def test_export_pack_is_deterministic(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DIRECTOR_PACKS_DIR", tmp_path / "installed")
    store.install(make_pack(tmp_path))
    out = tmp_path / "exported.vfdirector"
    store.export_pack("kvxw/knowledge-cinematic", "1.0.0", out)
    assert out.is_file()
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert "director-pack.yaml" in names
        assert names == sorted(names)


def test_derive_pack_forces_new_id_version_and_tracks_derived_from(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DIRECTOR_PACKS_DIR", tmp_path / "installed")
    store.install(make_pack(tmp_path))
    derived = store.derive_pack(
        "kvxw/knowledge-cinematic",
        "1.0.0",
        {"id": "kvxw/knowledge-cinematic-custom", "version": "1.0.0", "style": {"anchor": "cool palette"}},
    )
    assert derived.id == "kvxw/knowledge-cinematic-custom"
    assert derived.derivedFrom.id == "kvxw/knowledge-cinematic"
    assert derived.derivedFrom.version == "1.0.0"


def test_derive_pack_rejects_new_publisher_id(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DIRECTOR_PACKS_DIR", tmp_path / "installed")
    store.install(make_pack(tmp_path))
    with pytest.raises(store.DirectorPackStoreError) as exc:
        store.derive_pack(
            "kvxw/knowledge-cinematic",
            "1.0.0",
            {"id": "other/knowledge-cinematic", "version": "1.0.0", "style": {"anchor": "cool"}},
        )
    assert exc.value.code == "derive_requires_same_publisher"


def test_derive_pack_rejects_non_editable_field(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DIRECTOR_PACKS_DIR", tmp_path / "installed")
    store.install(make_pack(tmp_path))
    with pytest.raises(store.DirectorPackStoreError) as exc:
        store.derive_pack(
            "kvxw/knowledge-cinematic",
            "1.0.0",
            {"id": "kvxw/knowledge-cinematic-custom", "version": "1.0.0", "routing": {"default": ["stickman"]}},
        )
    assert exc.value.code == "derive_field_not_editable"


def test_disable_enable_and_uninstall(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DIRECTOR_PACKS_DIR", tmp_path / "installed")
    store.install(make_pack(tmp_path))
    disabled = store.set_pack_status("kvxw/knowledge-cinematic", "1.0.0", "disabled")
    assert disabled["status"] == "disabled"
    enabled = store.set_pack_status("kvxw/knowledge-cinematic", "1.0.0", "enabled")
    assert enabled["status"] == "enabled"
    store.uninstall("kvxw/knowledge-cinematic", "1.0.0")
    with pytest.raises(store.DirectorPackStoreError) as exc:
        store.get_pack("kvxw/knowledge-cinematic", "1.0.0")
    assert exc.value.code == "pack_not_installed"
