import io
import json
import re
import shutil
import zipfile
from urllib.parse import quote
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from config import JIANYING_DRAFT_DIR
from services.project_service import get_project, update_project, _project_dir, resolve_project_paths
from services.jobs import start_job
from adapters.jianying import generate_jianying_draft
from adapters.jianying_reader import parse_jianying_draft
from adapters.jianying_sync import apply_draft_params_to_project, select_draft_for_project
from engines.audio_analyzer import analyze_audio, generate_cue_points
from routers.render import _require_active_voiceover

router = APIRouter(tags=["export"])


# ── 全局配置/状态 ──

@router.get("/api/jianying-status")
def get_jianying_status():
    """查询剪映草稿目录状态（不依赖项目ID）"""
    found = JIANYING_DRAFT_DIR is not None
    return {
        "detected": found,
        "path": str(JIANYING_DRAFT_DIR.resolve()) if found else None,
        "drafts": _list_jianying_drafts() if found else []
    }


@router.get("/api/jianying-drafts/{folder}/params")
def get_jianying_draft_params(folder: str):
    """Read saved JianYing draft params such as clip scale and subtitle font size."""
    if not JIANYING_DRAFT_DIR:
        raise HTTPException(400, "未检测到剪映草稿目录")
    draft_dir = (JIANYING_DRAFT_DIR / folder).resolve()
    root = JIANYING_DRAFT_DIR.resolve()
    if root not in draft_dir.parents:
        raise HTTPException(400, "非法草稿路径")
    if not (draft_dir / "draft_content.json").exists():
        raise HTTPException(404, "草稿不存在或缺少 draft_content.json")
    try:
        return parse_jianying_draft(draft_dir)
    except Exception as e:
        raise HTTPException(500, f"读取剪映草稿参数失败: {e}") from e


@router.post("/api/projects/{project_id}/jianying/sync-params")
def sync_jianying_params(project_id: str, data: dict | None = None):
    """Sync editable scale/subtitle params from a saved JianYing draft back to this project."""
    if not JIANYING_DRAFT_DIR:
        raise HTTPException(400, "未检测到剪映草稿目录")
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    project_dict = p.model_dump()
    folder = (data or {}).get("folder")
    try:
        if folder:
            draft_dir = (JIANYING_DRAFT_DIR / str(folder)).resolve()
            root = JIANYING_DRAFT_DIR.resolve()
            if root not in draft_dir.parents:
                raise HTTPException(400, "非法草稿路径")
            matched_by = "selected"
        else:
            draft_dir, matched_by = select_draft_for_project(project_dict, JIANYING_DRAFT_DIR)
        draft_params = parse_jianying_draft(draft_dir)
        updated_dict, changes = apply_draft_params_to_project(project_dict, draft_params)
        updated_project = update_project(project_id, updated_dict)
        if not updated_project:
            raise HTTPException(404, "项目不存在")
        return {
            "status": "ok",
            "draftName": draft_dir.name,
            "draftPath": str(draft_dir),
            "matchedBy": matched_by,
            "changes": changes,
            "project": updated_project.model_dump(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"同步剪映参数失败: {e}") from e


# ── 项目特定导出 ──

@router.post("/api/projects/{project_id}/export/jianying")
def export_jianying(project_id: str, cue_mode: str | None = None, policy: str = "create_new"):
    """导出剪映草稿（ZIP 下载）"""
    if policy != "create_new":
        if policy == "replace_explicit":
            raise HTTPException(400, "replace_explicit is only supported by direct JianYing export")
        raise HTTPException(400, "policy must be create_new")
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    proj_dict = p.model_dump()
    proj_dict = resolve_project_paths(_project_dir(project_id), proj_dict)
    _require_active_voiceover(proj_dict)
    cue_points = _safe_cue_points(proj_dict, cue_mode)
    draft_dir = None
    try:
        zip_output_dir = _project_dir(project_id) / "exports" / ".jianying-zip"
        result = generate_jianying_draft(
            proj_dict, output_dir=zip_output_dir, cue_points=cue_points, policy="create_new"
        )
        draft_dir = result.final_path
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in draft_dir.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(draft_dir.parent))
        buf.seek(0)
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', p.name) or "export"
        filename = f"{safe_name}_draft.zip"
        response = StreamingResponse(
            buf,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename*=UTF-8\'\'{quote(filename)}',
                "X-VideoForge-Policy": result.policy,
                "X-VideoForge-Draft-Name": quote(result.final_path.name, safe=""),
                "X-VideoForge-Revision": str(result.revision),
            }
        )
        shutil.rmtree(draft_dir, ignore_errors=True)
        return response
    except Exception as e:
        if draft_dir is not None:
            shutil.rmtree(draft_dir, ignore_errors=True)
        raise HTTPException(500, str(e)) from e


@router.post("/api/projects/{project_id}/export/jianying-direct")
def export_jianying_direct(project_id: str, cue_mode: str | None = None, policy: str = "create_new", source_draft: str | None = None):
    """直接导出到剪映草稿目录（零解压，打开剪映即可见）"""
    if not JIANYING_DRAFT_DIR:
        raise HTTPException(400, "未检测到剪映草稿目录。请手动设置 JIANYING_DRAFT_DIR 环境变量。")

    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")

    proj_dict = p.model_dump()
    proj_dict = resolve_project_paths(_project_dir(project_id), proj_dict)
    _require_active_voiceover(proj_dict)
    cue_points = _safe_cue_points(proj_dict, cue_mode)
    try:
        result = generate_jianying_draft(
            proj_dict, output_dir=JIANYING_DRAFT_DIR, cue_points=cue_points,
            policy=policy, source_draft=source_draft, direct_export=True,
        )
        metadata = result.to_metadata()
        return JSONResponse({
            "status": "ok",
            "message": "已导出到剪映草稿目录",
            "path": metadata["finalPath"],
            "draft_name": metadata["draftName"],
            **metadata,
        })
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"直接导出到剪映失败: {str(e)}")


@router.post("/api/projects/{project_id}/export/jianying-direct/start")
def start_export_jianying_direct(project_id: str, cue_mode: str | None = None, policy: str = "create_new", source_draft: str | None = None):
    def work(update):
        update(8, "validate", "检查剪映目录")
        update(22, "prepare", "准备草稿数据")
        update(60, "export", "写入剪映草稿")
        result = export_jianying_direct(project_id, cue_mode, policy, source_draft)
        update(92, "finalize", "读取导出结果")
        if isinstance(result, JSONResponse):
            return json.loads(result.body.decode("utf-8"))
        return result

    return start_job("export-jianying-direct", work)


def _safe_cue_points(project: dict, cue_mode: str | None):
    """Best-effort cue points for JianYing export; failures fall back to existing timeline."""
    if not cue_mode or cue_mode == "uniform":
        return None
    segments = project.get("segments", [])
    image_count = len(segments)
    if image_count <= 0:
        return None
    bgm = project.get("audio", {}).get("bgm", {})
    tracks = bgm.get("tracks") or []
    bgm_path = tracks[0].get("file", "") if tracks else bgm.get("file", "")
    if not bgm_path or not Path(bgm_path).exists():
        return None
    try:
        return generate_cue_points(analyze_audio(bgm_path), image_count, cue_mode)
    except Exception:
        return None


def _list_jianying_drafts() -> list[dict]:
    """列出剪映中已有的草稿"""
    if not JIANYING_DRAFT_DIR:
        return []
    results = []
    for d in sorted(JIANYING_DRAFT_DIR.iterdir(), key=lambda x: x.name, reverse=True):
        if d.is_dir() and not d.name.startswith(".videoforge-") and (d / "draft_content.json").exists():
            meta = d / "draft_meta_info.json"
            name = d.name
            if meta.exists():
                try:
                    m = json.loads(meta.read_text(encoding="utf-8"))
                    name = m.get("draft_name", d.name)
                except Exception:
                    pass
            results.append({"name": name, "folder": d.name})
    return results
