from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from config import PROJECTS_DIR
from services.project_service import get_project, update_project
from visual_assets.contracts import (
    ExportOptions,
    GenerationBehavior,
    RoutingOptions,
    RenderConfig,
    VisualAssetRenderRequest,
    VisualAssetSource,
    VisualAssetSourceItem,
    VisualSemantic,
)
from visual_assets.hashing import file_sha256, hash_payload
from visual_assets.code_visual.motion_export import render_motion_mp4
from visual_assets.rasterizer import PillowSvgRasterizer, ResvgSvgRasterizer
from visual_assets.service import render_visual_asset_project

router = APIRouter(prefix="/api/projects/{project_id}/visual-assets/stickman", tags=["visual-assets"])
code_visual_router = APIRouter(prefix="/api/projects/{project_id}/visual-assets/code-visual", tags=["visual-assets"])


class StickmanRenderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sourceMode: Literal["visual_plan", "subtitles"] = "visual_plan"
    sceneIds: list[str] = Field(default_factory=list)
    exportSvg: bool = True
    exportPng: bool = True
    generateContactSheet: bool = True
    bindToProject: bool | None = None
    replaceManualEdits: bool = False
    forceReplaceUserAsset: bool = False
    routing: RoutingOptions = Field(default_factory=lambda: RoutingOptions(lowConfidencePolicy="fallback"))


class CodeVisualRenderBody(StickmanRenderBody):
    rendererId: Literal["auto", "white_sketch", "silhouette", "pixel_rules", "mechanism_diagram"] = "auto"
    themeMode: Literal["dark", "light"] | None = None
    ipPack: Literal["neutral", "xuanqi", "huicewolf", "ayin"] = "neutral"
    exportVideo: bool = True
    videoFps: int = Field(default=12, ge=6, le=30)
    presentationMode: Literal["main", "overlay"] = "main"
    overlayX: float = Field(default=0.5, ge=0, le=1)
    overlayY: float = Field(default=0.32, ge=0, le=1)
    overlayScale: float = Field(default=0.36, gt=0, le=1)
    overlayOpacity: float = Field(default=1.0, ge=0, le=1)
    overlayZIndex: int = Field(default=0, ge=0, le=32)
    overlayDurationPolicy: Literal["loop", "freeze_last_frame", "trim"] = "loop"


def _project_dir(project_id: str) -> Path:
    candidate = PROJECTS_DIR / project_id
    if candidate.parent != PROJECTS_DIR or Path(project_id).name != project_id:
        raise HTTPException(400, "invalid project id")
    return candidate


def _plan_items(project: dict, scene_ids: list[str]) -> tuple[list[VisualAssetSourceItem], dict[str, dict]]:
    episode = ((project.get("structuredContent") or {}).get("episode") or {})
    plan = episode.get("visualPlan") or {}
    scenes = plan.get("scenes") or []
    if not scenes:
        raise HTTPException(409, "visual_plan_missing")
    by_id = {str(scene.get("id")): scene for scene in scenes}
    requested = scene_ids or [str(scene.get("id")) for scene in scenes]
    missing = [scene_id for scene_id in requested if scene_id not in by_id]
    if missing:
        raise HTTPException(404, {"code": "visual_scene_missing", "sceneIds": missing})
    subtitles = {str(item.get("id")): item for item in project.get("subtitles") or []}
    items: list[VisualAssetSourceItem] = []
    for order, scene_id in enumerate(requested, 1):
        scene = by_id[scene_id]
        ids = list(scene.get("subtitleIds") or [])
        selected = [subtitles[item] for item in ids if item in subtitles]
        if not selected:
            raise HTTPException(409, {"code": "scene_subtitles_missing", "sceneId": scene_id})
        start, end = float(selected[0]["start"]), float(selected[-1]["end"])
        semantic = ((scene.get("metadata") or {}).get("semantic") or {})
        items.append(VisualAssetSourceItem(
            id=scene_id,
            order=order,
            blockId=str(scene.get("blockId") or "") or None,
            subtitleIds=ids,
            start=start,
            end=end,
            text="".join(str(item.get("text") or "") for item in selected) or str(scene.get("summary") or scene_id),
            semantic=VisualSemantic.model_validate(semantic),
        ))
    return items, by_id


def _subtitle_items(project: dict) -> list[VisualAssetSourceItem]:
    items = []
    for order, subtitle in enumerate(project.get("subtitles") or [], 1):
        items.append(VisualAssetSourceItem(
            id=str(subtitle.get("id") or f"subtitle_{order:03d}"),
            order=order,
            subtitleIds=[str(subtitle.get("id") or f"subtitle_{order:03d}")],
            start=float(subtitle.get("start", 0)),
            end=float(subtitle.get("end", 0)),
            text=str(subtitle.get("text") or ""),
            semantic=VisualSemantic.model_validate((subtitle.get("metadata") or {}).get("semantic") or {}),
        ))
    return items


def _provider_run_root(provider_id: str) -> str:
    return "code-visual" if provider_id == "code_visual_svg" else "stickman"


def _provider_run_prefix(provider_id: str) -> str:
    return provider_id.replace("_svg", "") + "_run_"


def _render_code_visual_videos(result, output_dir: Path, canvas: dict, fps: int) -> tuple[dict[str, dict], list[dict]]:
    manifest_path = output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"items": []}
    manifest_items = list(manifest.get("items") or [])
    by_segment = {str(item.get("segmentId")): item for item in manifest_items if isinstance(item, dict)}
    video_exports: dict[str, dict] = {}
    width = int(canvas.get("width", 1080) or 1080)
    height = int(canvas.get("height", 1920) or 1920)
    for item in result.items:
        if item.status not in {"generated", "fallback", "needs_review", "skipped_unchanged"}:
            continue
        if not item.svgPath or not item.motionPlanPath:
            continue
        manifest_item = by_segment.get(item.segmentId, {})
        existing_rel = manifest_item.get("videoPath")
        existing_path = output_dir / str(existing_rel or "")
        if existing_rel and existing_path.exists() and manifest_item.get("videoSha256") == file_sha256(existing_path):
            video_exports[item.segmentId] = {
                "videoPath": existing_rel,
                "videoSha256": manifest_item.get("videoSha256"),
            }
            continue
        sidecar = json.loads((output_dir / item.motionPlanPath).read_text(encoding="utf-8"))
        motion_plan = sidecar.get("motionPlan") or {}
        video_rel = f"assets/{Path(item.svgPath).stem}.mp4"
        video_path = output_dir / video_rel
        render_motion_mp4(
            output_dir / item.svgPath,
            motion_plan,
            video_path,
            width=width,
            height=height,
            fps=fps,
        )
        video_hash = file_sha256(video_path)
        manifest_item.update({"videoPath": video_rel, "videoSha256": video_hash})
        video_exports[item.segmentId] = {
            "videoPath": video_rel,
            "videoSha256": video_hash,
            "motionPlanPath": item.motionPlanPath,
            "duration": motion_plan.get("duration"),
        }
    if video_exports:
        manifest["items"] = manifest_items
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return video_exports, manifest_items


def _run(project_id: str, body: StickmanRenderBody, single_scene_id: str | None = None, provider_id: str = "stickman_svg") -> dict:
    project_model = get_project(project_id)
    if project_model is None:
        raise HTTPException(404, "project_not_found")
    project = project_model.model_dump(mode="python")
    bind = body.bindToProject if body.bindToProject is not None else body.sourceMode == "visual_plan"
    selected_ids = [single_scene_id] if single_scene_id else body.sceneIds
    if body.sourceMode == "visual_plan":
        items, scenes = _plan_items(project, selected_ids)
    else:
        items, scenes = _subtitle_items(project), {}
        bind = False if body.bindToProject is None else bind
    source = VisualAssetSource(mode="inline_segments", segments=items)
    request = VisualAssetRenderRequest(
        projectId=project_id,
        source=source,
        routing=body.routing,
        exports=ExportOptions(svg=body.exportSvg, png=body.exportPng, manifest=True, contactSheet=body.generateContactSheet, generationReport=True),
        renderer=RenderConfig(provider=provider_id, providerVersion="0.5.0" if provider_id == "code_visual_svg" else "0.1.0", providerOptions=({"rendererId": body.rendererId, "themeMode": body.themeMode, "ipPack": body.ipPack} if provider_id == "code_visual_svg" else {})),
        behavior=GenerationBehavior(existingOutputPolicy="skip_unchanged", protectManualEdits=True, replaceManualEdits=body.replaceManualEdits, segmentId=single_scene_id),
    )
    run_hash = hash_payload({"projectId": request.projectId, "source": request.source.model_dump(mode="python"), "renderer": request.renderer.model_dump(mode="python"), "exports": request.exports.model_dump(mode="python")})
    run_id = _provider_run_prefix(provider_id) + run_hash[:12]
    run_root = _provider_run_root(provider_id)
    output_dir = _project_dir(project_id) / "visual-assets" / run_root / run_id
    result = render_visual_asset_project(request, output_dir, ResvgSvgRasterizer() if provider_id == "code_visual_svg" else PillowSvgRasterizer())
    video_exports, response_items = ({}, [item.model_dump(mode="json") for item in result.items])
    if provider_id == "code_visual_svg" and isinstance(body, CodeVisualRenderBody) and body.exportVideo:
        video_exports, response_items = _render_code_visual_videos(result, output_dir, project.get("canvas") or {}, body.videoFps)
    bindings, conflicts = [], []
    if bind:
        assets = list(project.get("assets") or [])
        asset_dir = _project_dir(project_id) / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        segment_updates: dict[str, dict] = {}
        overlay_updates: dict[str, dict] = {}
        for item in result.items:
            scene = scenes.get(item.segmentId)
            has_png = item.pngPath is not None
            has_video = item.segmentId in video_exports
            if scene is None or (not has_png and not has_video) or item.status not in {"generated", "fallback", "needs_review", "skipped_unchanged"}:
                continue
            asset_id = (
                f"visual_code_visual_overlay_{item.segmentId}"
                if provider_id == "code_visual_svg"
                and isinstance(body, CodeVisualRenderBody)
                and body.presentationMode == "overlay"
                else f"visual_{provider_id.replace('_svg', '')}_{item.segmentId}"
            )
            existing_ids = (
                [asset_id]
                if provider_id == "code_visual_svg"
                and isinstance(body, CodeVisualRenderBody)
                and body.presentationMode == "overlay"
                else list(scene.get("visualAssetIds") or [])
            )
            existing = [asset for asset in assets if asset.get("id") in existing_ids]
            provider_assets = [asset for asset in existing if (asset.get("metadata") or {}).get("generatedBy") == "visual_asset_provider"]
            user_assets = [asset for asset in existing if asset not in provider_assets]
            if user_assets and not body.forceReplaceUserAsset:
                conflicts.append({"sceneId": item.segmentId, "code": "user_asset_conflict"})
                continue
            if provider_assets and not body.replaceManualEdits:
                manually_changed = False
                for asset in provider_assets:
                    metadata = asset.get("metadata") or {}
                    asset_path = _project_dir(project_id) / str(asset.get("path") or "")
                    expected_hash = metadata.get("videoSha256") or metadata.get("pngSha256") or metadata.get("contentSha256")
                    if metadata.get("manualOverride") or not asset_path.exists() or (expected_hash and file_sha256(asset_path) != expected_hash):
                        manually_changed = True
                        break
                if manually_changed:
                    conflicts.append({"sceneId": item.segmentId, "code": "manual_override_protected"})
                    continue
            if has_video:
                exported = video_exports[item.segmentId]
                filename = Path(exported["videoPath"]).name
                source_asset = output_dir / exported["videoPath"]
                target_asset = asset_dir / filename
                asset_type = "video"
                content_hash = exported["videoSha256"]
            else:
                filename = Path(item.pngPath).name
                source_asset = output_dir / item.pngPath
                target_asset = asset_dir / filename
                asset_type = "image"
                content_hash = item.pngSha256
            if not target_asset.exists() or content_hash != next((a.get("metadata", {}).get("contentSha256") or a.get("metadata", {}).get("videoSha256") or a.get("metadata", {}).get("pngSha256") for a in assets if a.get("id") == asset_id), None):
                shutil.copy2(source_asset, target_asset)
            record = {
                "id": asset_id,
                "type": asset_type,
                "name": filename,
                "path": f"assets/{filename}",
                "metadata": {
                    "generatedBy": "visual_asset_provider",
                    "provider": provider_id,
                    "providerVersion": result.providerVersion,
                    "sceneId": item.segmentId,
                    "templateId": item.templateId,
                    "templateVersion": item.templateVersion,
                    "inputHash": item.inputHash,
                    "svgPath": f"visual-assets/{run_root}/{run_id}/{item.svgPath}",
                    "motionPlanPath": f"visual-assets/{run_root}/{run_id}/{item.motionPlanPath}" if item.motionPlanPath else None,
                    "videoPath": f"visual-assets/{run_root}/{run_id}/{video_exports[item.segmentId]['videoPath']}" if has_video else None,
                    "pngSha256": item.pngSha256,
                    "videoSha256": video_exports[item.segmentId]["videoSha256"] if has_video else None,
                    "contentSha256": content_hash,
                    "motionPlan": item.motionHint.get("motionPlan") if item.motionHint else None,
                    "motionLayerIds": item.motionHint.get("layerIds") if item.motionHint else None,
                    "manualOverride": False,
                    "transform": {"x": 0.5, "y": 0.46, "scale": 0.9, "rotation": 0, "fit": "contain"},
                },
            }
            assets = [asset for asset in assets if asset.get("id") != asset_id]
            assets.append(record)
            is_code_overlay = (
                provider_id == "code_visual_svg"
                and isinstance(body, CodeVisualRenderBody)
                and body.presentationMode == "overlay"
            )
            if is_code_overlay:
                metadata = dict(scene.get("metadata") or {})
                overlay_ids = [value for value in list(metadata.get("videoOverlayIds") or []) if value != asset_id]
                metadata["videoOverlayIds"] = [*overlay_ids, asset_id]
                scene["metadata"] = metadata
                overlay_id = f"code_visual_overlay_{item.segmentId}"
                overlay_updates[overlay_id] = {
                    "id": overlay_id,
                    "assetId": asset_id,
                    "start": item.start,
                    "end": item.end,
                    "x": body.overlayX,
                    "y": body.overlayY,
                    "scale": body.overlayScale,
                    "opacity": body.overlayOpacity,
                    "durationPolicy": body.overlayDurationPolicy,
                    "zIndex": body.overlayZIndex,
                }
                bindings.append({"sceneId": item.segmentId, "assetId": asset_id, "mode": "overlay"})
            else:
                scene["visualAssetIds"] = [asset_id]
                scene["primaryAssetId"] = asset_id
                bindings.append({"sceneId": item.segmentId, "assetId": asset_id, "mode": "main"})
            if provider_id == "code_visual_svg" and not is_code_overlay:
                segment_updates[item.segmentId] = {
                    "id": f"visual_code_visual_{item.segmentId}_segment",
                    "assetPath": f"assets/{filename}",
                    "type": asset_type,
                    "start": item.start,
                    "end": item.end,
                    "sourceStart": 0,
                    "transform": record["metadata"]["transform"],
                    "metadata": {"sceneId": item.segmentId, "assetId": asset_id, "generatedBy": "visual_asset_provider", "provider": provider_id},
                }
        if bindings:
            payload = {"assets": assets, "structuredContent": project["structuredContent"]}
            if overlay_updates:
                overlays = dict(project.get("overlays") or {})
                existing_overlays = [
                    overlay for overlay in list(overlays.get("videoOverlays") or [])
                    if str(overlay.get("id") or "") not in overlay_updates
                ]
                overlays["videoOverlays"] = [
                    *existing_overlays,
                    *sorted(overlay_updates.values(), key=lambda overlay: (overlay["zIndex"], overlay["start"], overlay["id"])),
                ]
                payload["overlays"] = overlays
            if provider_id == "code_visual_svg" and segment_updates:
                replacement_segment_ids = {entry["id"] for entry in segment_updates.values()}
                existing_segments = [
                    segment for segment in list(project.get("segments") or [])
                    if str(segment.get("id") or "") not in replacement_segment_ids
                ]
                provider_scene_ids = set(segment_updates)
                existing_segments = [
                    segment for segment in existing_segments
                    if not ((segment.get("metadata") or {}).get("provider") == provider_id and (segment.get("metadata") or {}).get("sceneId") in provider_scene_ids)
                ]
                payload["segments"] = sorted([*existing_segments, *segment_updates.values()], key=lambda segment: (float(segment.get("start", 0) or 0), str(segment.get("id") or "")))
            updated = update_project(project_id, payload)
            if updated is None:
                raise HTTPException(404, "project_not_found")
    return {
        "runId": result.runId,
        "status": "partial" if conflicts and result.status == "succeeded" else result.status,
        "manifest": f"visual-assets/{run_root}/{run_id}/manifest.json",
        "generationReport": f"visual-assets/{run_root}/{run_id}/generation_report.json",
        "contactSheet": f"visual-assets/{run_root}/{run_id}/contact_sheet.png" if result.contactSheetPngPath else f"visual-assets/{run_root}/{run_id}/contact_sheet.svg",
        "items": response_items,
        "videoExports": list(video_exports.values()),
        "bindings": bindings,
        "conflicts": conflicts,
        "warnings": result.warnings,
        "errors": [error.model_dump(mode="json") for error in result.errors],
    }


@router.post("/render")
def render_stickman_assets(project_id: str, body: StickmanRenderBody):
    return _run(project_id, body)


@router.post("/scenes/{scene_id}/regenerate")
def regenerate_stickman_scene(project_id: str, scene_id: str, body: StickmanRenderBody):
    return _run(project_id, body, scene_id)


@code_visual_router.post("/render")
def render_code_visual_assets(project_id: str, body: CodeVisualRenderBody):
    return _run(project_id, body, provider_id="code_visual_svg")


@code_visual_router.post("/scenes/{scene_id}/regenerate")
def regenerate_code_visual_scene(project_id: str, scene_id: str, body: CodeVisualRenderBody):
    return _run(project_id, body, scene_id, provider_id="code_visual_svg")


@router.get("/runs/{run_id}")
def get_stickman_generation_run(project_id: str, run_id: str):
    if Path(run_id).name != run_id or not run_id.startswith("stickman_run_"):
        raise HTTPException(400, "invalid_run_id")
    root = _project_dir(project_id) / "visual-assets" / "stickman" / run_id
    if not root.exists():
        raise HTTPException(404, "run_not_found")
    import json
    def read(name):
        path = root / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    return {
        "runId": run_id,
        "manifest": read("manifest.json"),
        "generationReport": read("generation_report.json"),
        "contactSheet": f"visual-assets/stickman/{run_id}/contact_sheet.png" if (root / "contact_sheet.png").exists() else f"visual-assets/stickman/{run_id}/contact_sheet.svg",
    }
