"""Global asset library — shared across all projects."""
import json
import os
import re
import shutil
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse
from config import PROJECTS_DIR

router = APIRouter(prefix="/api/library", tags=["library"])

LIBRARY_DIR = PROJECTS_DIR / "_library"
INDEX_FILE = LIBRARY_DIR / "index.json"

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
AUDIO_EXTS = {".mp3", ".wav", ".aac", ".ogg", ".m4a"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
MAX_FILENAME_LENGTH = 180


def _safe_display_name(raw_name: str | None) -> str:
    name = Path(str(raw_name or "")).name.strip()
    if not name or name in {".", ".."}:
        raise HTTPException(400, "文件名不能为空")
    if any(ord(char) < 32 for char in name) or re.search(r'[<>:"/\\|?*]', name):
        raise HTTPException(400, "文件名包含 Windows 不支持的字符")
    return name[:MAX_FILENAME_LENGTH]


def _ensure_dir():
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)


def _load_index() -> list[dict]:
    _ensure_dir()
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_index(items: list[dict]):
    _ensure_dir()
    INDEX_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _classify(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in IMAGE_EXTS:
        return "image"
    # ponytail: 默认当视频处理——未知媒体文件不会炸渲染器，但 "other" 会让 Pydantic 崩
    return "video"


def _project_asset_payload(item: dict) -> dict:
    """Project Asset-compatible payload for a library item."""
    return {
        "id": item["id"],
        "name": item["filename"],
        "path": item["path"],
        "type": item["type"],
        "metadata": {"libraryFolder": item.get("folder", "")},
    }


def _folder_matches(item_folder: str, folder_name: str) -> bool:
    return item_folder == folder_name or item_folder.startswith(folder_name + "/")


@router.get("")
def list_library_assets():
    """List all assets in the global library."""
    return _load_index()


@router.post("/migrate-folders")
def migrate_folders():
    """Fix existing assets: extract folder from filename if folder field is missing."""
    items = _load_index()
    fixed = 0
    for item in items:
        if item.get("folder"):
            continue  # already has folder
        fname = item.get("filename", "")
        if "/" in fname:
            parts = fname.rsplit("/", 1)
            item["folder"] = parts[0]
            item["filename"] = parts[1]
            fixed += 1
        elif "\\" in fname:
            parts = fname.rsplit("\\", 1)
            item["folder"] = parts[0]
            item["filename"] = parts[1]
            fixed += 1
    if fixed:
        _save_index(items)
    return {"status": "ok", "fixed": fixed, "total": len(items)}


@router.post("")
async def upload_to_library(file: UploadFile = File(...), request: Request = None):
    """Upload a file to the global library. Preserves folder structure from webkitdirectory uploads.

    Only accepts media files (.mp4, .mov, .jpg, .png, .mp3, .m4a, etc.).
    Rejects non-media files (.zip, .json, .bat, .ps1, .md, .txt, etc.).
    """
    _ensure_dir()

    # Reject non-media files before saving
    raw_name = file.filename or "unknown"
    ext = Path(raw_name).suffix.lower()
    if ext not in MEDIA_EXTS:
        raise HTTPException(400, f"不支持的文件类型 '{ext}'，仅支持图片/视频/音频文件")

    asset_id = f"lib_{uuid.uuid4().hex[:12]}"

    # Try multiple sources to extract the full path (including folder)
    raw_name = file.filename or "unknown"
    full_path = raw_name

    # Source 1: Content-Disposition header (most reliable for webkitdirectory)
    cd = request.headers.get("content-disposition", "") if request else ""
    if cd:
        # Match filename*=UTF-8''path (RFC 5987)
        m_star = re.search(r"filename\*=UTF-8''([^;\"\s]+)", cd)
        if m_star:
            full_path = m_star.group(1)
        else:
            m = re.search(r'filename="?([^";\s]+)"?', cd)
            if m:
                full_path = m.group(1)

    # Source 2: multipart form data raw body (fallback)
    if request and full_path == raw_name:
        try:
            body = await request.body()
            # Look for filename= in raw multipart headers
            raw = body[:4096].decode("latin-1", errors="ignore")
            m3 = re.search(r'filename\*=UTF-8\'\'([^\s;]+)', raw)
            if m3:
                full_path = m3.group(1)
        except Exception:
            pass

    # Extract folder from full path
    folder = ""
    if "/" in full_path:
        parts = full_path.rsplit("/", 1)
        folder = parts[0]
        display_name = parts[1]
    elif "\\" in full_path:
        parts = full_path.rsplit("\\", 1)
        folder = parts[0]
        display_name = parts[1]
    else:
        display_name = full_path

    display_name = _safe_display_name(display_name)

    ext = Path(display_name).suffix.lower()
    safe_name = f"{asset_id}{ext}"
    dest = LIBRARY_DIR / safe_name

    temp = LIBRARY_DIR / f".upload-{uuid.uuid4().hex}.tmp"
    size = 0
    try:
        with temp.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "素材超过 2 GB 限制")
                handle.write(chunk)
        temp.replace(dest)
    finally:
        temp.unlink(missing_ok=True)

    item = {
        "id": asset_id,
        "filename": display_name,
        "stored_name": safe_name,
        "folder": folder,
        "path": str(dest),
        "type": _classify(display_name),
        "size": size,
    }
    items = _load_index()
    items.append(item)
    _save_index(items)
    return item


@router.delete("/{asset_id}")
def delete_library_asset(asset_id: str):
    """Delete an asset from the global library."""
    items = _load_index()
    target = None
    rest = []
    for item in items:
        if item["id"] == asset_id:
            target = item
        else:
            rest.append(item)
    if not target:
        raise HTTPException(404, "Asset not found")
    # Delete file
    try:
        p = Path(target["path"])
        if p.exists():
            p.unlink()
    except Exception:
        pass
    _save_index(rest)
    return {"status": "deleted", "id": asset_id}


@router.get("/raw/{filename}")
def serve_library_asset(filename: str):
    """Serve a library asset file for preview / playback."""
    path = LIBRARY_DIR / filename
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path)


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v"}
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS

# Maximum assets per project to prevent runaway imports
MAX_ASSETS = 50


@router.post("/import-folder/{folder_name}/to/{project_id}")
def import_folder_to_project(folder_name: str, project_id: str):
    """Reference all assets from a library folder in a project."""
    items = _load_index()
    folder_items = [
        i for i in items
        if _folder_matches(i.get("folder", ""), folder_name)
    ]
    if not folder_items:
        raise HTTPException(404, f"文件夹 '{folder_name}' 中没有素材")

    # Only import media files (images/videos/audio), skip .zip/.json/.bat etc.
    imported_all = [
        _project_asset_payload(item)
        for item in folder_items
        if Path(item["path"]).exists()
        and Path(item["path"]).suffix.lower() in MEDIA_EXTS
    ]

    # Cap at MAX_ASSETS to avoid overwhelming projects
    imported = imported_all[:MAX_ASSETS]

    if not imported:
        raise HTTPException(400, f"文件夹 '{folder_name}' 中没有可导入的媒体文件")

    # Defensive: check asset count before import
    from services.project_service import get_project, update_project
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "项目不存在")

    current_assets = [a.model_dump() if hasattr(a, "model_dump") else a for a in (project.assets or [])]
    if len(current_assets) + len(imported) > MAX_ASSETS:
        raise HTTPException(
            400,
            f"素材数量超出限制：当前 {len(current_assets)} 个，"
            f"将导入 {len(imported)} 个，共 {len(current_assets) + len(imported)} 个。"
            f"上限为 {MAX_ASSETS} 个。请缩小文件夹范围或删除已有素材。",
        )

    # Deduplicate
    new_assets = [a for a in imported if not any(x.get("id") == a["id"] for x in current_assets)]

    if not new_assets:
        return {"status": "ok", "imported": 0, "folder": folder_name, "message": "所有素材已存在于项目中"}

    # Use update_project to ensure Pydantic validation — never write raw JSON
    update_project(project_id, {"assets": current_assets + new_assets})
    return {"status": "ok", "imported": len(new_assets), "folder": folder_name}


@router.post("/import/{asset_id}/to/{project_id}")
def import_to_project(asset_id: str, project_id: str):
    """Copy a library asset into a project's assets directory."""
    items = _load_index()
    target = next((i for i in items if i["id"] == asset_id), None)
    if not target:
        raise HTTPException(404, "Library asset not found")

    src = Path(target["path"])
    if not src.exists():
        raise HTTPException(404, "Library file missing from disk")

    # Only allow media files
    if src.suffix.lower() not in MEDIA_EXTS:
        raise HTTPException(400, f"不支持的文件类型: {src.suffix}")

    # Defensive: check asset count
    from services.project_service import get_project, update_project
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "项目不存在")

    current_assets = [a.model_dump() if hasattr(a, "model_dump") else a for a in (project.assets or [])]
    if len(current_assets) >= MAX_ASSETS:
        raise HTTPException(400, f"素材数量已达上限 {MAX_ASSETS} 个，请先删除一些素材")

    new_asset = _project_asset_payload(target)

    if any(a.get("id") == new_asset["id"] for a in current_assets):
        return {"status": "skipped", "asset_id": asset_id, "message": "素材已存在"}

    # Use update_project for Pydantic validation — never write raw JSON
    update_project(project_id, {"assets": current_assets + [new_asset]})

    return {
        "status": "imported",
        "asset_id": asset_id,
        "project_id": project_id,
        "path": new_asset["path"],
        "type": new_asset["type"],
        "filename": target["filename"],
    }
