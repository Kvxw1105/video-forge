import json
import os
import uuid
import shutil
import logging
from pathlib import Path
from datetime import datetime
from pydantic import ValidationError
from config import PROJECTS_DIR
from models.project import Project

logger = logging.getLogger(__name__)


class ProjectLoadError(RuntimeError):
    pass


def _project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id


def _project_file(project_id: str) -> Path:
    return _project_dir(project_id) / "project.json"


def resolve_project_paths(proj_dir: Path, proj_dict: dict) -> dict:
    """把 project dict 里的相对路径（voiceover/bgm/segments.assetPath）解析成绝对路径。
    供 renderer 和 jianying adapter 使用,这两个都要求绝对路径才能找到素材文件。"""
    audio = proj_dict.get("audio") or {}
    vo = audio.get("voiceover") or {}
    if vo.get("file") and not Path(vo["file"]).is_absolute():
        abs_p = proj_dir / vo["file"]
        if abs_p.exists():
            vo["file"] = str(abs_p)
    # Resolve multi-voiceover versions too (active export/preview depends on them).
    for multi_vo in audio.get("voiceovers") or []:
        if not isinstance(multi_vo, dict):
            continue
        file_path = multi_vo.get("file", "")
        if file_path and not Path(file_path).is_absolute():
            abs_p = proj_dir / file_path
            if abs_p.exists():
                multi_vo["file"] = str(abs_p)
    bgm = audio.get("bgm") or {}
    if bgm.get("file") and not Path(bgm["file"]).is_absolute():
        abs_p = proj_dir / bgm["file"]
        if abs_p.exists():
            bgm["file"] = str(abs_p)
    for seg in proj_dict.get("segments", []):
        ap = seg.get("assetPath", "")
        if ap and not Path(ap).is_absolute():
            abs_p = proj_dir / ap
            if abs_p.exists():
                seg["assetPath"] = str(abs_p)
    tracks = bgm.get("tracks") or []
    for track in tracks:
        fp = track.get("file", "")
        if fp and not Path(fp).is_absolute():
            abs_p = proj_dir / fp
            if abs_p.exists():
                track["file"] = str(abs_p)
    return proj_dict


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Lists and non-dict values are replaced, not merged."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def create_project(name: str, canvas_ratio: str = "9:16", template_id: str | None = None) -> Project:
    pid = f"proj_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    now = datetime.now().isoformat()
    project_data = Project(id=pid, name=name, created_at=now, updated_at=now).model_dump()

    if template_id:
        from services.template_service import get_template

        template = get_template(template_id)
        if template is None:
            raise ValueError(f"Template not found: {template_id}")
        reusable_keys = (
            "templateId", "visualMode", "canvas", "overlays", "audio",
            "timeline", "perImageDuration", "shuffleMode",
        )
        template_config = {key: template[key] for key in reusable_keys if key in template}
        project_data = _deep_merge(project_data, template_config)
    else:
        w, h = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350), "4:3": (1440, 1080)}.get(canvas_ratio, (1080, 1920))
        project_data["canvas"] = _deep_merge(project_data["canvas"], {
            "width": w,
            "height": h,
            "ratio": canvas_ratio,
        })

    project_data.update({"id": pid, "name": name, "created_at": now, "updated_at": now})
    project = Project(**project_data)
    project.exportSettings.outputDir = str(_project_dir(pid))
    _save_project(project)
    return project


def _repair_json_text(text: str) -> str:
    """Repair the common corruption case where project.json ends with extra braces.

    We still should fix raw writers, but this keeps one bad save from making the
    whole project look deleted to the frontend.
    """
    decoder = json.JSONDecoder()
    obj, end = decoder.raw_decode(text)
    tail = text[end:].strip()
    if tail and set(tail) <= {"}"}:
        return text[:end]
    return text


def get_project(project_id: str) -> Project | None:
    f = _project_file(project_id)
    if not f.exists():
        return None
    try:
        text = f.read_text(encoding="utf-8")
        repaired_file = False
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            repaired = _repair_json_text(text)
            raw = json.loads(repaired)
            repaired_file = True
        project = Project(**raw)
        if repaired_file:
            _save_project(project)
        return project
    except (json.JSONDecodeError, ValidationError, OSError) as e:
        logger.exception("Failed to load project %s from %s", project_id, f)
        raise ProjectLoadError(f"项目文件读取失败 {project_id} ({f}): {type(e).__name__}: {e}") from e


def update_project(project_id: str, data: dict) -> Project | None:
    """Update project using deep dict merge — avoids Pydantic model_copy issues with nested dicts."""
    p = get_project(project_id)
    if not p:
        return None
    try:
        # Convert current project to dict, deep merge, then reconstruct
        current = p.model_dump()
        merged = _deep_merge(current, data)
        merged["updated_at"] = datetime.now().isoformat()

        # Reconstruct Project from merged dict
        updated = Project(**merged)
        _save_project(updated)
        return updated
    except Exception as e:
        logger.error("update_project failed for %s: %s", project_id, e)
        logger.error("Data keys: %s", list(data.keys()))
        logger.error("Data sample: %s", str(data)[:500])
        import traceback
        traceback.print_exc()
        raise


def list_projects() -> list[dict]:
    results = []
    if not PROJECTS_DIR.exists():
        return results
    for d in sorted(PROJECTS_DIR.iterdir(), key=lambda x: x.name, reverse=True):
        if d.is_dir() and (d / "project.json").exists():
            try:
                p = json.loads((d / "project.json").read_text(encoding="utf-8"))
                results.append({"id": p["id"], "name": p["name"], "created_at": p.get("created_at", "")})
            except Exception:
                continue
    return results


def _trash_dir() -> Path:
    return PROJECTS_DIR / ".trash"


def delete_project(project_id: str) -> dict | None:
    d = _project_dir(project_id)
    if not d.is_dir() or not (d / "project.json").exists():
        return None
    trash_root = _trash_dir()
    trash_root.mkdir(parents=True, exist_ok=True)
    deleted_at = datetime.now().isoformat()
    trash_id = f"{project_id}__{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    project = get_project(project_id)
    info = {
        "trashId": trash_id,
        "projectId": project_id,
        "name": project.name if project else project_id,
        "created_at": project.created_at if project else "",
        "deleted_at": deleted_at,
    }
    (d / ".trashinfo.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.move(str(d), str(trash_root / trash_id))
    return info


def list_deleted_projects() -> list[dict]:
    trash_root = _trash_dir()
    if not trash_root.exists():
        return []
    items = []
    for entry in trash_root.iterdir():
        info_file = entry / ".trashinfo.json"
        if not entry.is_dir() or not info_file.exists():
            continue
        try:
            items.append(json.loads(info_file.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to read trash metadata: %s", info_file)
    return sorted(items, key=lambda item: item.get("deleted_at", ""), reverse=True)


def restore_project(trash_id: str) -> Project | None:
    if Path(trash_id).name != trash_id:
        return None
    source = _trash_dir() / trash_id
    info_file = source / ".trashinfo.json"
    if not source.is_dir() or not info_file.exists():
        return None
    info = json.loads(info_file.read_text(encoding="utf-8"))
    project_id = str(info.get("projectId") or "")
    if not project_id or Path(project_id).name != project_id:
        return None
    destination = _project_dir(project_id)
    if destination.exists():
        raise FileExistsError(project_id)
    shutil.move(str(source), str(destination))
    restored_info = destination / ".trashinfo.json"
    if restored_info.exists():
        restored_info.unlink()
    return get_project(project_id)


def _save_project(project: Project):
    d = _project_dir(project.id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "assets").mkdir(exist_ok=True)
    target = _project_file(project.id)
    temp = target.with_name(f"{target.name}.tmp")
    backup = target.with_name(f"{target.name}.bak")
    payload = project.model_dump_json(indent=2)

    try:
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        if target.exists():
            try:
                json.loads(target.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
            else:
                shutil.copy2(target, backup)
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
