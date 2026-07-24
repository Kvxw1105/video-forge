from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .cache import atomic_write_json, atomic_write_text, read_json
from .contact_sheet import build_contact_sheet_svg
from .contracts import GenerationError, GenerationReport, VisualAssetGenerationResult, VisualAssetManifest, VisualAssetManifestItem, VisualAssetRenderRequest, normalize_subtitles
from .hashing import file_sha256, hash_payload, input_hash_payload
from .naming import asset_filename
from .rasterizer import SvgRasterizer, validate_png_alpha
from .registry import get_provider
from .stickman.renderer import validate_svg


def _source_items(request: VisualAssetRenderRequest):
    if request.source.mode == "inline_segments":
        return list(request.source.segments)
    if request.source.mode == "subtitles":
        return normalize_subtitles(request.source.subtitles)
    return list(request.source.segments)


def _manifest_item(item, route, input_hash, status, rendered=None, svg_path=None, png_path=None, svg_hash=None, png_hash=None, error=None, warnings=None):
    return VisualAssetManifestItem(
        segmentId=item.id,
        order=item.order,
        blockId=item.blockId,
        subtitleIds=item.subtitleIds,
        start=item.start,
        end=item.end,
        duration=round(item.end - item.start, 6),
        text=item.text,
        semantic=item.semantic.model_dump(mode="python"),
        templateId=route.templateId,
        templateVersion=route.templateVersion,
        confidence=route.confidence,
        templateParameters=route.parameters,
        svgPath=svg_path,
        pngPath=png_path,
        svgSha256=svg_hash,
        pngSha256=png_hash,
        composition=rendered.composition if rendered else {},
        motionHint=rendered.motionHint if rendered else {},
        inputHash=input_hash,
        status=status,
        fallbackUsed=route.fallbackUsed,
        manualOverride=status == "manual_override",
        warnings=warnings or [],
        error=error,
    )


def render_visual_asset_project(request: VisualAssetRenderRequest, output_dir: Path, rasterizer: SvgRasterizer | None = None) -> VisualAssetGenerationResult:
    provider = get_provider(request.renderer.provider)
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    report_path = output_dir / "generation_report.json"
    events_path = output_dir / "events.jsonl"
    prior_raw = read_json(manifest_path) or {}
    prior_items = {item.get("segmentId"): item for item in prior_raw.get("items", []) if isinstance(item, dict)}
    items = sorted(_source_items(request), key=lambda x: x.order)
    if request.behavior.segmentId:
        selected = {request.behavior.segmentId}
        unchanged_prior = [VisualAssetManifestItem.model_validate(item) for sid, item in prior_items.items() if sid not in selected]
        items = [item for item in items if item.id in selected]
    else:
        unchanged_prior = []
    manifest_items = sorted(unchanged_prior, key=lambda x: x.order)
    errors: list[GenerationError] = []
    warnings: list[str] = []
    png_status = "not_requested"
    run_hash = hash_payload({"projectId": request.projectId, "source": request.source.model_dump(mode="python"), "renderer": request.renderer.model_dump(mode="python"), "exports": request.exports.model_dump(mode="python")})

    for item in items:
        route = provider.route(item, request.routing)
        item_hash = hash_payload(input_hash_payload(item, route, request.renderer, request.exports))
        svg_name = asset_filename(item.order, item.id, route.templateId, "svg")
        png_name = asset_filename(item.order, item.id, route.templateId, "png")
        svg_rel = f"assets/{svg_name}"
        png_rel = f"assets/{png_name}"
        svg_path = output_dir / svg_rel
        png_path = output_dir / png_rel
        prior = prior_items.get(item.id)
        if prior and prior.get("inputHash") == item_hash and svg_path.exists() and svg_path.stat().st_size > 0:
            current_svg_hash = file_sha256(svg_path)
            if current_svg_hash == prior.get("svgSha256") and not validate_svg(svg_path.read_text(encoding="utf-8"), request.renderer.canvas.width, request.renderer.canvas.height):
                if not request.exports.png or (png_path.exists() and prior.get("pngSha256") == file_sha256(png_path)):
                    manifest_items.append(VisualAssetManifestItem.model_validate({**prior, "status": "skipped_unchanged"}))
                    atomic_write_text(events_path, (events_path.read_text(encoding="utf-8") if events_path.exists() else "") + f"skipped {item.id}\n")
                    continue
            if request.behavior.protectManualEdits and not request.behavior.replaceManualEdits:
                manifest_items.append(_manifest_item(item, route, item_hash, "manual_override", svg_path=svg_rel, png_path=prior.get("pngPath"), svg_hash=current_svg_hash, png_hash=prior.get("pngSha256"), warnings=["existing output hash differs from manifest"]))
                continue
        if request.behavior.existingOutputPolicy == "fail_on_existing" and svg_path.exists() and not prior:
            err = GenerationError(code="output_conflict", message="output exists", segmentId=item.id)
            errors.append(err); manifest_items.append(_manifest_item(item, route, item_hash, "failed", error=err)); continue
        rendered = provider.render_svg(item, route, request.renderer)
        svg_errors = validate_svg(rendered.svg, request.renderer.canvas.width, request.renderer.canvas.height)
        if svg_errors:
            err = GenerationError(code="svg_validation_failed", message="; ".join(svg_errors), segmentId=item.id, templateId=route.templateId)
            errors.append(err); manifest_items.append(_manifest_item(item, route, item_hash, "failed", rendered, error=err)); continue
        atomic_write_text(svg_path, rendered.svg)
        svg_hash = file_sha256(svg_path)
        item_status = "needs_review" if route.needsReview else ("fallback" if route.fallbackUsed else "generated")
        png_hash = None
        if request.exports.png:
            png_status = "unavailable"
            if rasterizer is None or not rasterizer.is_available():
                warnings.append("png_converter_unavailable")
            else:
                png_status = "failed"
                result = rasterizer.rasterize(svg_path, png_path, request.renderer.canvas.width, request.renderer.canvas.height)
                if result.succeeded and png_path.exists():
                    alpha_errors = validate_png_alpha(png_path, request.renderer.canvas.width, request.renderer.canvas.height)
                    if alpha_errors:
                        errors.append(GenerationError(code="png_alpha_invalid", message="; ".join(alpha_errors), segmentId=item.id))
                    else:
                        png_hash = file_sha256(png_path)
                        png_status = "succeeded"
                else:
                    errors.append(GenerationError(code=result.error_code or "png_render_failed", message=result.message, segmentId=item.id))
        manifest_items.append(_manifest_item(item, route, item_hash, item_status, rendered, svg_rel, png_rel if png_hash else None, svg_hash, png_hash))
        manifest = VisualAssetManifest(projectId=request.projectId, provider=provider.provider_id, providerVersion=provider.provider_version, visualPlanId=request.source.visualPlanId, visualSourceHash=request.source.visualSourceHash, inputHash=run_hash, items=sorted(manifest_items, key=lambda x: x.order))
        atomic_write_json(manifest_path, manifest.model_dump(mode="json"))
        atomic_write_text(events_path, (events_path.read_text(encoding="utf-8") if events_path.exists() else "") + f"generated {item.id}\n")

    manifest = VisualAssetManifest(projectId=request.projectId, provider=provider.provider_id, providerVersion=provider.provider_version, visualPlanId=request.source.visualPlanId, visualSourceHash=request.source.visualSourceHash, inputHash=run_hash, items=sorted(manifest_items, key=lambda x: x.order))
    atomic_write_json(manifest_path, manifest.model_dump(mode="json"))
    contact_path = None
    contact_png = None
    if request.exports.contactSheet:
        contact_path = build_contact_sheet_svg(manifest, output_dir / "contact_sheet.svg")
        if request.exports.png and rasterizer is not None and rasterizer.is_available():
            try:
                root = ET.parse(contact_path).getroot()
                contact_width = int(float(root.attrib.get("width", "1080")))
                contact_height = int(float(root.attrib.get("height", "360")))
                contact_png = output_dir / "contact_sheet.png"
                contact_result = rasterizer.rasterize(contact_path, contact_png, contact_width, contact_height)
                if not contact_result.succeeded:
                    warnings.append("contact_sheet_png_unavailable")
                    contact_png = None
            except Exception:
                warnings.append("contact_sheet_png_unavailable")
                contact_png = None
    failed = sum(1 for item in manifest.items if item.status == "failed")
    manual = sum(1 for item in manifest.items if item.status == "manual_override")
    skipped = sum(1 for item in manifest.items if item.status == "skipped_unchanged")
    status = "failed" if failed == len(manifest.items) and failed else ("partial" if errors or warnings or manual or png_status in {"unavailable", "failed"} else "succeeded")
    report = GenerationReport(projectId=request.projectId, provider=provider.provider_id, providerVersion=provider.provider_version, status=status, itemCount=len(manifest.items), generatedCount=sum(1 for item in manifest.items if item.status in {"generated", "fallback", "needs_review"}), skippedCount=skipped, manualOverrideCount=manual, failedCount=failed, pngStatus=png_status, errors=errors, warnings=sorted(set(warnings)), rasterizer={"id": getattr(rasterizer, "rasterizer_id", None), "available": bool(rasterizer and rasterizer.is_available())})
    atomic_write_json(report_path, report.model_dump(mode="json"))
    return VisualAssetGenerationResult(runId="stickman_run_" + run_hash[:12], projectId=request.projectId, visualPlanId=request.source.visualPlanId, visualSourceHash=request.source.visualSourceHash, inputHash=run_hash, provider=provider.provider_id, providerVersion=provider.provider_version, status=status, manifestPath=str(manifest_path), contactSheetPath=str(contact_path) if contact_path else None, contactSheetPngPath=str(contact_png) if contact_png else None, generationReportPath=str(report_path), items=manifest.items, errors=errors, warnings=sorted(set(warnings)))
