"""Install, list, read, enable, disable, export, derive and uninstall Director Packs.

Installation is immutable per ``id + version``: reinstalling the exact same
digest is idempotent, a different digest for the same identity conflicts.
Uninstall only touches the installed pack directory, never Projects,
candidates, assets, bindings, Previews or JianYing drafts.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import DIRECTOR_PACKS_DIR
from models.director_pack import DirectorPackManifest, PACK_ID, SEMVER
from .director_pack_archive import ENTRYPOINT, DirectorPackArchiveError, inspect_archive

SOURCE_TRUST = ("LOCAL", "UNVERIFIED", "TRUSTED_BUILTIN")
PACK_STATUS = ("enabled", "enabled_with_degradation", "disabled", "blocked")

# Repository-shipped packs: <repo>/director_packs/builtin/<publisher>/<slug>/<version>/
BUILTIN_PACKS_DIR = Path(__file__).resolve().parents[2] / "director_packs" / "builtin"

INSTALLATION_FILE = "installation.json"
_FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_MAX_ATOMIC_RETRIES = 3


class DirectorPackStoreError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _install_dir(pack_id: str, version: str) -> Path:
    publisher, slug = pack_id.split("/", 1)
    return DIRECTOR_PACKS_DIR / publisher / slug / version


def _read_installation(dir_path: Path) -> dict[str, Any]:
    record_path = dir_path / INSTALLATION_FILE
    if not record_path.is_file():
        raise DirectorPackStoreError("pack_not_installed", f"director pack is not installed: {dir_path}")
    return json.loads(record_path.read_text(encoding="utf-8"))


def _atomic_replace(source: Path, target: Path) -> None:
    for attempt in range(_MAX_ATOMIC_RETRIES):
        try:
            source.replace(target)
            return
        except PermissionError:
            if attempt == _MAX_ATOMIC_RETRIES - 1:
                raise
            time.sleep(0.2)


def _install_directory(record: dict[str, Any], files: dict[str, bytes], installed_dir: Path) -> None:
    """Write files plus installation.json into a fresh temp dir, then publish."""
    staging = installed_dir.parent / f".{installed_dir.name}.staging-{time.time_ns()}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        for name, data in files.items():
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (staging / INSTALLATION_FILE).write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        installed_dir.parent.mkdir(parents=True, exist_ok=True)
        if installed_dir.exists():
            _atomic_replace(staging, installed_dir)
        else:
            _atomic_replace(staging, installed_dir)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def install(pack_path: Path, *, source_trust: str = "LOCAL") -> dict[str, Any]:
    if source_trust not in SOURCE_TRUST:
        raise DirectorPackStoreError("invalid_source_trust", f"unknown source trust: {source_trust!r}")
    inspected = inspect_archive(pack_path)
    manifest = DirectorPackManifest.model_validate(inspected.manifest)
    record = {
        "id": manifest.id,
        "version": manifest.version,
        "manifestDigest": inspected.manifest_digest,
        "archiveDigest": inspected.archive_digest,
        "sourceTrust": source_trust,
        "status": "enabled",
        "degradations": [],
        "installedAt": _utc_now(),
    }
    installed_dir = _install_dir(manifest.id, manifest.version)
    if installed_dir.exists():
        existing = _read_installation(installed_dir)
        if existing.get("archiveDigest") == inspected.archive_digest:
            return existing
        raise DirectorPackStoreError(
            "immutable_version_conflict",
            f"{manifest.id}@{manifest.version} is already installed with a different digest",
        )
    _install_directory(record, inspected.entries, installed_dir)
    return record


def install_builtin(pack_id: str, version: str) -> dict[str, Any]:
    """Install a repository-shipped built-in pack as TRUSTED_BUILTIN.

    Built-in packs live under ``director_packs/builtin/<publisher>/<slug>/<version>/``
    in the repository. Their files are packaged into a temporary archive with
    fixed zip timestamps (so the archive digest is stable across installs) and
    then passed through the normal immutable ``install()`` path.
    """
    if "/" not in pack_id:
        raise DirectorPackStoreError("invalid_pack_id", f"pack id must be publisher/slug: {pack_id!r}")
    publisher, slug = pack_id.split("/", 1)
    builtin_dir = BUILTIN_PACKS_DIR / publisher / slug / version
    if not builtin_dir.is_dir():
        raise DirectorPackStoreError(
            "builtin_pack_not_found", f"builtin pack directory not found: {builtin_dir}"
        )
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / f"{slug}-{version}.vfdirector"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(builtin_dir.rglob("*")):
                if not path.is_file():
                    continue
                arcname = path.relative_to(builtin_dir).as_posix()
                info = zipfile.ZipInfo(arcname, _FIXED_ZIP_TIMESTAMP)
                zf.writestr(info, path.read_bytes())
        return install(zip_path, source_trust="TRUSTED_BUILTIN")


def list_packs() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not DIRECTOR_PACKS_DIR.is_dir():
        return result
    for publisher_dir in sorted(DIRECTOR_PACKS_DIR.iterdir()):
        if not publisher_dir.is_dir():
            continue
        for slug_dir in sorted(publisher_dir.iterdir()):
            if not slug_dir.is_dir():
                continue
            for version_dir in sorted(slug_dir.iterdir()):
                record_path = version_dir / INSTALLATION_FILE
                if record_path.is_file():
                    result.append(json.loads(record_path.read_text(encoding="utf-8")))
    return result


def get_pack(pack_id: str, version: str) -> dict[str, Any]:
    installed_dir = _install_dir(pack_id, version)
    record = _read_installation(installed_dir)
    manifest_path = installed_dir / ENTRYPOINT
    if manifest_path.is_file():
        import yaml

        record["manifest"] = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    return record


def _require_installed(pack_id: str, version: str) -> Path:
    installed_dir = _install_dir(pack_id, version)
    _read_installation(installed_dir)
    return installed_dir


def set_pack_status(pack_id: str, version: str, status: str) -> dict[str, Any]:
    if status not in PACK_STATUS:
        raise DirectorPackStoreError("invalid_status", f"unknown pack status: {status!r}")
    installed_dir = _require_installed(pack_id, version)
    record = _read_installation(installed_dir)
    record["status"] = status
    (installed_dir / INSTALLATION_FILE).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def export_pack(pack_id: str, version: str, output_path: Path) -> Path:
    installed_dir = _require_installed(pack_id, version)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(installed_dir.rglob("*")):
            if path.is_file() and path.name != INSTALLATION_FILE:
                info = zipfile.ZipInfo(path.relative_to(installed_dir).as_posix(), _FIXED_ZIP_TIMESTAMP)
                zf.writestr(info, path.read_bytes())
    return output_path


def uninstall(pack_id: str, version: str) -> None:
    installed_dir = _require_installed(pack_id, version)
    shutil.rmtree(installed_dir)


# ── derive ──

_EDITABLE_LEAF_DEFAULTS = {
    "style.anchor",
    "rhythm.visualDensity",
    "candidates.count",
    "approval.defaultMode",
}


def _editable_paths(manifest: DirectorPackManifest) -> set[str]:
    paths = {str(item) for item in manifest.editable}
    if not paths:
        paths = set(_EDITABLE_LEAF_DEFAULTS)
    return paths


def _changed_leaves(changes: dict[str, Any], prefix: str = "") -> set[str]:
    leaves: set[str] = set()
    for key, value in changes.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            leaves |= _changed_leaves(value, path)
        else:
            leaves.add(path)
    return leaves


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    node = target
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def derive_pack(pack_id: str, version: str, changes: dict[str, Any]) -> DirectorPackManifest:
    """Derive a new manifest from an installed pack.

    Only paths listed in the source ``editable`` (plus the identity fields)
    may change. The derived pack always gets a new id and version and records
    ``derivedFrom``; no runtime inheritance is established.
    """
    if "id" not in changes or "version" not in changes:
        raise DirectorPackStoreError(
            "derive_requires_identity", "derived pack requires a new id and version"
        )
    new_id = str(changes["id"])
    new_version = str(changes["version"])
    publisher, _ = pack_id.split("/", 1)
    new_publisher, _ = new_id.split("/", 1)
    if new_publisher != publisher:
        raise DirectorPackStoreError(
            "derive_requires_same_publisher",
            f"derived pack must keep publisher {publisher!r}",
        )
    if new_id == pack_id and new_version == version:
        raise DirectorPackStoreError(
            "derive_requires_new_identity",
            "derived pack must change id or version",
        )
    installed_dir = _require_installed(pack_id, version)
    import yaml

    source_manifest = DirectorPackManifest.model_validate(
        yaml.safe_load((installed_dir / ENTRYPOINT).read_text(encoding="utf-8"))
    )
    editable = _editable_paths(source_manifest)
    editable |= {"id", "version"}
    changed = _changed_leaves(changes)
    forbidden = changed - editable
    if forbidden:
        raise DirectorPackStoreError(
            "derive_field_not_editable",
            f"fields are not editable for this pack: {sorted(forbidden)}",
        )

    merged = json.loads(source_manifest.model_dump_json())
    merged["id"] = new_id
    merged["version"] = new_version
    merged["derivedFrom"] = {"id": pack_id, "version": version}
    for path, value in changes.items():
        if path in {"id", "version", "derivedFrom"}:
            continue
        if isinstance(value, dict):
            for leaf in _changed_leaves(value, path):
                _set_path(merged, leaf, _leaf_value(changes, leaf))
        else:
            _set_path(merged, path, value)
    return DirectorPackManifest.model_validate(merged)


def _leaf_value(source: dict[str, Any], path: str) -> Any:
    node = source
    for part in path.split("."):
        node = node[part]
    return node
