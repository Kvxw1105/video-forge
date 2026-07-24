from __future__ import annotations

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
    run_id = "stickman_run_" + run_hash[:12]
    output_dir = _project_dir(project_id) / "visual-assets" / "stickman" / run_id
    result = render_visual_asset_project(request, output_dir, ResvgSvgRasterizer() if provider_id == "code_visual_svg" else PillowSvgRasterizer())
    bindings, conflicts = [], []
    if bind:
        assets = list(project.get("assets") or [])
        asset_dir = _project_dir(project_id) / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        for item in result.items:
            scene = scenes.get(item.segmentId)
            if scene is None or item.pngPath is None or item.status not in {"generated", "fallback", "needs_review", "skipped_unchanged"}:
                continue
            existing_ids = list(scene.get("visualAssetIds") or [])
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
                    expected_hash = metadata.get("pngSha256")
                    if metadata.get("manualOverride") or not asset_path.exists() or (expected_hash and file_sha256(asset_path) != expected_hash):
                        manually_changed = True
                        break
                if manually_changed:
                    conflicts.append({"sceneId": item.segmentId, "code": "manual_override_protected"})
                    continue
            asset_id = f"visual_{provider_id.replace('_svg', '')}_{item.segmentId}"
            filename = Path(item.pngPath).name
            source_png = output_dir / item.pngPath
            target_png = asset_dir / filename
            if not target_png.exists() or item.pngSha256 != next((a.get("metadata", {}).get("pngSha256") for a in assets if a.get("id") == asset_id), None):
                shutil.copy2(source_png, target_png)
            record = {
                "id": asset_id,
                "type": "image",
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
                    "svgPath": f"visual-assets/stickman/{run_id}/{item.svgPath}",
                    "pngSha256": item.pngSha256,
                    "manualOverride": False,
                    "transform": {"x": 0.5, "y": 0.46, "scale": 0.9, "rotation": 0, "fit": "contain"},
                },
            }
            assets = [asset for asset in assets if asset.get("id") != asset_id]
            assets.append(record)
            scene["visualAssetIds"] = [asset_id]
            scene["primaryAssetId"] = asset_id
            bindings.append({"sceneId": item.segmentId, "assetId": asset_id})
        if bindings:
            updated = update_project(project_id, {"assets": assets, "structuredContent": project["structuredContent"]})
            if updated is None:
                raise HTTPException(404, "project_not_found")
    return {
        "runId": result.runId,
        "status": "partial" if conflicts and result.status == "succeeded" else result.status,
        "manifest": f"visual-assets/stickman/{run_id}/manifest.json",
        "generationReport": f"visual-assets/stickman/{run_id}/generation_report.json",
        "contactSheet": f"visual-assets/stickman/{run_id}/contact_sheet.png" if result.contactSheetPngPath else f"visual-assets/stickman/{run_id}/contact_sheet.svg",
        "items": [item.model_dump(mode="json") for item in result.items],
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
