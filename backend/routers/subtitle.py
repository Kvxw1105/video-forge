"""SRT subtitle import and export routes."""
import re
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, Response, UploadFile

from services.project_service import get_project, update_project
from shared.srt import decode_srt, parse_srt, serialize_srt, subtitles_to_transcript


router = APIRouter(prefix="/api/projects/{project_id}/subtitles", tags=["subtitles"])


@router.post("/import-srt")
async def import_srt(project_id: str, file: UploadFile = File(...)):
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")

    try:
        text = decode_srt(await file.read())
        subtitles, ignored_count = parse_srt(text)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    current_style = {
        "fontSize": 48,
        "color": "#ffffff",
        "strokeColor": "#000000",
        "strokeWidth": 2,
        "position": "bottom_center",
    }
    if p.subtitles:
        first = p.subtitles[0]
        existing_style = first.get("style", {}) if isinstance(first, dict) else getattr(first, "style", {})
        current_style.update(existing_style or {})
    for sub in subtitles:
        sub["style"] = dict(current_style)

    script = subtitles_to_transcript(subtitles)
    updated = update_project(project_id, {"script": script, "subtitles": subtitles})
    if not updated:
        raise HTTPException(404, "项目不存在")
    return {
        "subtitleCount": len(subtitles),
        "ignoredCount": ignored_count,
        "script": script,
        "subtitles": subtitles,
        "project": updated.model_dump(),
    }


@router.get("/export-srt")
def export_srt(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    if not p.subtitles:
        raise HTTPException(400, "当前项目没有可导出的字幕")

    subtitles = [item if isinstance(item, dict) else item.model_dump() for item in p.subtitles]
    content = serialize_srt(subtitles)
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', p.name).strip() or "subtitles"
    filename = quote(f"{safe_name}.srt")
    return Response(
        content=b"\xef\xbb\xbf" + content.encode("utf-8"),
        media_type="application/x-subrip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
