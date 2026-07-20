import shutil
import mimetypes
import re
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from services.project_service import get_project, _project_dir

router = APIRouter(prefix="/api/projects/{project_id}/assets", tags=["assets"])

MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
MAX_FILENAME_LENGTH = 180


def _safe_upload_name(raw_name: str | None) -> str:
    name = Path(str(raw_name or "")).name.strip()
    if not name or name in {".", ".."}:
        raise HTTPException(400, "文件名不能为空")
    if any(ord(char) < 32 for char in name) or re.search(r'[<>:"/\\|?*]', name):
        raise HTTPException(400, "文件名包含 Windows 不支持的字符")
    return name[:MAX_FILENAME_LENGTH]


def _safe_resolve(proj_dir: Path, user_path: str) -> Path:
    """Resolve user_path safely within proj_dir, preventing path traversal."""
    if Path(user_path).is_absolute():
        candidate = Path(user_path).resolve()
        if proj_dir.resolve() in [candidate, *candidate.parents]:
            return candidate
        return proj_dir / "__nonexistent__"

    for base in (proj_dir, proj_dir / "assets"):
        candidate = (base / user_path).resolve()
        if proj_dir.resolve() in [candidate, *candidate.parents]:
            return candidate
    return proj_dir / "__nonexistent__"


@router.get("/stream")
def stream_asset(project_id: str, path: str, filename: str = ""):
    """Stream any file safely — handles both relative and absolute paths.

    Query params:
      path: relative path under project dir, or absolute path within project/library dirs
      filename: optional override for Content-Disposition
    """
    proj_dir = _project_dir(project_id)

    # Try relative path first
    candidate = _safe_resolve(proj_dir, path)

    # If not found, try as absolute path (for BGM files stored with full path)
    if not candidate.exists() and Path(path).is_absolute():
        abs_path = Path(path).resolve()
        # Safety: must be under project dir or library dir
        lib_dir = (proj_dir.parent / "_library").resolve()
        if proj_dir.resolve() in [abs_path, *abs_path.parents] or lib_dir in [abs_path, *abs_path.parents]:
            candidate = abs_path

    if not candidate.exists():
        raise HTTPException(404, "文件不存在")

    mt, _ = mimetypes.guess_type(str(candidate))
    return FileResponse(str(candidate), media_type=mt or "application/octet-stream")

@router.post("")
async def upload_asset(project_id: str, file: UploadFile = File(...)):
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    proj_dir = _project_dir(project_id)
    assets_dir = proj_dir / "assets"
    assets_dir.mkdir(exist_ok=True)
    filename = _safe_upload_name(file.filename)
    dest = assets_dir / filename
    if dest.exists():
        dest = assets_dir / f"{dest.stem}_{uuid.uuid4().hex[:8]}{dest.suffix}"
    temp = assets_dir / f".upload-{uuid.uuid4().hex}.tmp"
    size = 0
    try:
        with temp.open("wb") as handle:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "素材超过 2 GB 限制")
                handle.write(chunk)
        temp.replace(dest)
    finally:
        temp.unlink(missing_ok=True)
    return {"filename": filename, "name": filename, "path": str(dest), "size": size, "type": "image" if dest.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"} else "audio" if dest.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac"} else "video"}

@router.get("/raw/{filename:path}")
def serve_asset(project_id: str, filename: str):
    """Serve raw asset file (images, audio) for browser preview"""
    proj_dir = _project_dir(project_id)
    file_path = _safe_resolve(proj_dir, filename)
    if not file_path.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(str(file_path))

@router.get("/project-file/{filename:path}")
def serve_project_file(project_id: str, filename: str):
    """Serve any file from project directory (voiceover.mp3, subtitles.srt, etc.).

    Also falls back to the global library for legacy projects that referenced
    lib_* assets via project-file URLs.
    """
    proj_dir = _project_dir(project_id)
    file_path = _safe_resolve(proj_dir, filename)
    if not file_path.exists():
        library_roots = [
            (proj_dir.parent / "_library").resolve(),
            (Path(__file__).resolve().parents[2] / "projects" / "_library").resolve(),
        ]
        for lib_dir in library_roots:
            lib_candidate = (lib_dir / Path(filename).name).resolve()
            if lib_dir in [lib_candidate, *lib_candidate.parents] and lib_candidate.exists():
                file_path = lib_candidate
                break
    if not file_path.exists():
        raise HTTPException(404, "文件不存在")
    response = FileResponse(str(file_path))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
