"""HTTP boundary for the Director Pack protocol v1.

Exposes the same install / list / read / resolve / export / derive /
enable / disable / uninstall lifecycle as the store, with fixed error
bodies ``{"code": ..., "message": ...}`` that never leak local paths.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.background import BackgroundTask

from services import director_pack_store as store
from services import director_policy_resolver as resolver
from services.director_pack_archive import DirectorPackArchiveError, MAX_ARCHIVE_BYTES

router = APIRouter(prefix="/api/director-packs", tags=["director-packs"])

_NOT_FOUND_CODES = {"pack_not_installed", "builtin_pack_not_found"}


def _safe_message(message: str) -> str:
    """Replace local filesystem paths inside an error message."""
    for path in (
        str(getattr(store, "DIRECTOR_PACKS_DIR", "")),
        str(getattr(store, "BUILTIN_PACKS_DIR", "")),
    ):
        if path and path in message:
            message = message.replace(path, "director-packs")
    return message


def _error(error: Exception):
    if isinstance(error, store.DirectorPackStoreError):
        if error.code in _NOT_FOUND_CODES:
            status = 404
        elif error.code == "immutable_version_conflict" or error.code.startswith("derive_requires_"):
            status = 409
        else:
            status = 422
        raise HTTPException(status, {"code": error.code, "message": _safe_message(str(error))}) from error
    if isinstance(error, (DirectorPackArchiveError, resolver.DirectorPackResolveError)):
        raise HTTPException(422, {"code": error.code, "message": _safe_message(str(error))}) from error
    if isinstance(error, ValidationError):
        raise HTTPException(422, {"code": "invalid_manifest", "message": str(error)}) from error
    raise error


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runMode: Literal["auto", "review"] = "auto"


@router.get("")
def list_packs():
    return store.list_packs()


@router.post("/import")
def import_pack(file: UploadFile = File(...)):
    staging = None
    try:
        staging = Path(tempfile.mkdtemp(prefix="director-pack-import-"))
        target = staging / "pack.vfdirector"
        size = 0
        with target.open("wb") as handle:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_ARCHIVE_BYTES:
                    raise DirectorPackArchiveError("archive_too_large", "upload exceeds 50 MB limit")
                handle.write(chunk)
        return store.install(target)
    except Exception as error:
        _error(error)
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


@router.get("/{publisher}/{slug}/{version}")
def get_pack(publisher: str, slug: str, version: str):
    try:
        return store.get_pack(f"{publisher}/{slug}", version)
    except Exception as error:
        _error(error)


@router.post("/{publisher}/{slug}/{version}/resolve")
def resolve_pack(publisher: str, slug: str, version: str, body: ResolveRequest):
    try:
        policy = resolver.resolve_installed(
            f"{publisher}/{slug}",
            version,
            body.runMode,
            authorization={"externalAllowed": False, "paidAllowed": False, "maxCostPerRun": 0},
        )
        return policy.model_dump(mode="json")
    except Exception as error:
        _error(error)


@router.get("/{publisher}/{slug}/{version}/export")
def export_pack(publisher: str, slug: str, version: str):
    staging = None
    try:
        staging = Path(tempfile.mkdtemp(prefix="director-pack-export-"))
        output = store.export_pack(
            f"{publisher}/{slug}", version, staging / f"{slug}-{version}.vfdirector"
        )
        return FileResponse(
            output,
            media_type="application/zip",
            filename=f"{slug}-{version}.vfdirector",
            background=BackgroundTask(shutil.rmtree, staging, ignore_errors=True),
        )
    except Exception as error:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
        _error(error)


@router.post("/{publisher}/{slug}/{version}/derive")
def derive_pack(publisher: str, slug: str, version: str, body: dict):
    try:
        manifest = store.derive_pack(f"{publisher}/{slug}", version, body)
        return manifest.model_dump()
    except Exception as error:
        _error(error)


@router.post("/{publisher}/{slug}/{version}/enable")
def enable_pack(publisher: str, slug: str, version: str):
    try:
        return store.set_pack_status(f"{publisher}/{slug}", version, "enabled")
    except Exception as error:
        _error(error)


@router.post("/{publisher}/{slug}/{version}/disable")
def disable_pack(publisher: str, slug: str, version: str):
    try:
        return store.set_pack_status(f"{publisher}/{slug}", version, "disabled")
    except Exception as error:
        _error(error)


@router.delete("/{publisher}/{slug}/{version}")
def uninstall_pack(publisher: str, slug: str, version: str):
    try:
        store.uninstall(f"{publisher}/{slug}", version)
        return {"ok": True}
    except Exception as error:
        _error(error)
