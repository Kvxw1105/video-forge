"""Safe extraction and inspection for Director Pack archives.

A Director Pack is a restricted ZIP archive whose entrypoint is
``director-pack.yaml``. No executable content may survive inspection;
every member path is normalized and validated, YAML is loaded with
``yaml.safe_load`` and the entrypoint must be a mapping.
"""
from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath, Path

import yaml

ALLOWED_SUFFIXES = {".yaml", ".yml", ".json", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".md"}
EXECUTABLE_SUFFIXES = {".py", ".pyc", ".js", ".mjs", ".cjs", ".exe", ".dll", ".bat", ".cmd", ".ps1", ".sh"}
MAX_FILES = 200
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
ENTRYPOINT = "director-pack.yaml"

# SVG members may not carry executable or remote content: a pack without
# ``.js`` members could otherwise smuggle embedded scripts, remote
# references or event handlers through a plain ``.svg`` file.
SVG_FORBIDDEN_PATTERNS = (
    "<script",
    "foreignobject",
    "javascript:",
    "http://",
    "https://",
    "onload=",
    "onclick=",
)


class DirectorPackArchiveError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class InspectedArchive:
    manifest: dict
    manifest_digest: str
    archive_digest: str
    entries: dict[str, bytes]


def validate_svg_content(text: str) -> None:
    """Reject executable or remote content inside an SVG member.

    The archive suffix whitelist already forbids ``.js`` members, so an
    attacker could otherwise smuggle embedded scripts, external references
    or event handlers through a plain ``.svg`` file. Matching is
    case-insensitive on purpose: ``<SCRIPT>`` and ``onLoad=`` must be caught
    too. ``http://`` and ``https://`` are rejected even though they can
    appear in legitimate data — the protocol forbids remote references.
    """
    lowered = text.lower()
    for pattern in SVG_FORBIDDEN_PATTERNS:
        if pattern in lowered:
            raise DirectorPackArchiveError(
                "svg_invalid_content", f"forbidden content in SVG: {pattern!r}"
            )


def _normalize_path(name: str) -> str:
    if "\\" in name:
        candidate = str(PureWindowsPath(name).as_posix())
    else:
        candidate = name
    return PurePosixPath(candidate).as_posix().lstrip("./")


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    if info.create_system == 3:  # Unix
        mode = (info.external_attr >> 16) & 0o170000
        if mode == 0o120000:  # S_IFLNK
            return True
    return False


def _check_entry(name: str, info: zipfile.ZipInfo, data_length: int) -> str:
    normalized = _normalize_path(name)
    if _is_symlink(info):
        raise DirectorPackArchiveError("unsafe_symlink", f"symlink entries are not allowed: {name!r}")
    raw = name.replace("\\", "/")
    if raw.startswith("/") or raw.startswith("//"):
        raise DirectorPackArchiveError("unsafe_path", f"absolute path is not allowed: {name!r}")
    if len(raw) > 1 and raw[1] == ":":
        raise DirectorPackArchiveError("unsafe_path", f"drive path is not allowed: {name!r}")
    parts = PurePosixPath(normalized).parts
    if ".." in parts:
        raise DirectorPackArchiveError("unsafe_path", f"parent traversal is not allowed: {name!r}")
    suffix = PurePosixPath(normalized).suffix.lower()
    if suffix in EXECUTABLE_SUFFIXES:
        raise DirectorPackArchiveError("executable_payload", f"executable payload is not allowed: {name!r}")
    if suffix not in ALLOWED_SUFFIXES:
        raise DirectorPackArchiveError("executable_payload", f"unknown file type is not allowed: {name!r}")
    if data_length > MAX_FILE_BYTES:
        raise DirectorPackArchiveError("file_too_large", f"member exceeds {MAX_FILE_BYTES} bytes: {name!r}")
    return normalized


def inspect_archive(path: Path) -> InspectedArchive:
    """Validate the archive and return the parsed manifest plus digests."""
    path = Path(path)
    size = path.stat().st_size
    if size > MAX_ARCHIVE_BYTES:
        raise DirectorPackArchiveError("archive_too_large", f"archive exceeds {MAX_ARCHIVE_BYTES} bytes")

    manifest_raw = b""
    manifest_digest = ""
    entries: dict[str, bytes] = {}
    expanded = 0
    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_FILES:
            raise DirectorPackArchiveError("too_many_files", f"archive exceeds {MAX_FILES} members")
        for info in infos:
            if info.is_dir():
                continue
            name = info.filename
            if name == ENTRYPOINT:
                manifest_raw = zf.read(info)
                manifest_digest = "sha256:" + hashlib.sha256(manifest_raw).hexdigest()
                normalized = _normalize_path(name)
                entries[normalized] = manifest_raw
                continue
            normalized = _check_entry(name, info, info.file_size)
            data = zf.read(info)
            if len(data) > MAX_FILE_BYTES:
                raise DirectorPackArchiveError("file_too_large", f"member exceeds {MAX_FILE_BYTES} bytes: {name!r}")
            if PurePosixPath(normalized).suffix.lower() == ".svg":
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    raise DirectorPackArchiveError(
                        "svg_invalid_content", f"SVG member is not valid UTF-8 text: {name!r}"
                    ) from None
                validate_svg_content(text)
            expanded += len(data)
            if expanded > MAX_EXPANDED_BYTES:
                raise DirectorPackArchiveError("archive_too_large", "expanded archive exceeds size limit")
            if normalized in entries:
                raise DirectorPackArchiveError("duplicate_path", f"duplicate normalized path: {normalized!r}")
            entries[normalized] = data

    if not manifest_raw:
        raise DirectorPackArchiveError("missing_entrypoint", f"missing entrypoint {ENTRYPOINT!r}")

    try:
        parsed = yaml.safe_load(io.BytesIO(manifest_raw))
    except yaml.YAMLError as exc:
        raise DirectorPackArchiveError("entrypoint_invalid_yaml", f"invalid YAML in {ENTRYPOINT}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise DirectorPackArchiveError("entrypoint_not_mapping", f"{ENTRYPOINT} must be a YAML mapping")

    archive_digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return InspectedArchive(
        manifest=parsed,
        manifest_digest=manifest_digest,
        archive_digest=archive_digest,
        entries=entries,
    )
