from __future__ import annotations

import json
import mimetypes
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import PROJECTS_DIR
from services.project_service import get_project, update_project

from .contracts import MediaExecutionRecord, MediaExecutionRequest
from .mediakit_provider import MediaKitError, MediaKitProvider


def _project_dir(project_id: str) -> Path:
    root = PROJECTS_DIR / project_id
    if root.parent != PROJECTS_DIR or Path(project_id).name != project_id:
        raise ValueError("invalid project id")
    return root


def _source_path(project: dict[str, Any], request: MediaExecutionRequest, root: Path) -> tuple[Path, str | None]:
    if request.sourceAssetId:
        asset = next((item for item in project.get("assets", []) if item.get("id") == request.sourceAssetId), None)
        if asset is None:
            raise ValueError("source asset not found")
        candidate = (root / str(asset.get("path") or "")).resolve()
        if root.resolve() not in [candidate, *candidate.parents]:
            raise ValueError("source asset path is outside project")
        return candidate, str(asset["id"])
    if request.sourcePath:
        candidate = (root / request.sourcePath).resolve()
        if root.resolve() not in [candidate, *candidate.parents]:
            raise ValueError("source path is outside project")
        return candidate, None
    raise ValueError("sourceAssetId or sourcePath is required")


def _output_path(root: Path, source: Path, request: MediaExecutionRequest) -> Path | None:
    if request.capability == "media.probe":
        return None
    suffix = ".mp3" if request.capability == "audio.extract" else ".mp4"
    name = request.outputName or f"{source.stem}_{request.capability.replace('.', '_')}{suffix}"
    name = Path(name).name
    if Path(name).suffix.lower() != suffix:
        name = f"{Path(name).stem}{suffix}"
    return root / "media-processing" / "mediakit" / "outputs" / f"{uuid.uuid4().hex[:8]}_{name}"


def execute(project_id: str, request: MediaExecutionRequest, provider: MediaKitProvider | None = None) -> dict[str, Any]:
    model = get_project(project_id)
    if model is None:
        raise KeyError("project_not_found")
    project, root = model.model_dump(mode="python"), _project_dir(project_id)
    source, source_asset_id = _source_path(project, request, root)
    provider = provider or MediaKitProvider()
    token = request.idempotencyToken or uuid.uuid4().hex
    record_id = f"mediakit_{uuid.uuid4().hex[:12]}"
    output = _output_path(root, source, request)
    record = MediaExecutionRecord(id=record_id, status="running", idempotencyToken=token, capability=request.capability, sourceAssetId=source_asset_id, sourcePath=str(source.relative_to(root)), parameters=request.model_dump(mode="json", exclude_none=True), privacyMode=request.privacyMode)
    root_run = root / "media-processing" / "mediakit" / "runs"
    root_run.mkdir(parents=True, exist_ok=True)
    record_path = root_run / f"{record_id}.json"
    try:
        result = provider.execute(request, source, output)
        reported = result.get("output_path") or result.get("outputPath") or result.get("file_path") or result.get("video_url") or result.get("audio_url")
        actual_output = output if output else None
        if reported and output and Path(reported).resolve() != output.resolve():
            raise MediaKitError("MediaKit output path did not match requested path", details={"reported": reported, "expected": str(output)})
        if actual_output:
            probe = provider.verify_media(actual_output)
            assets = list(project.get("assets") or [])
            asset_id = f"mediakit_{request.capability.replace('.', '_')}_{record_id[-8:]}"
            target = root / "assets" / actual_output.name
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(actual_output, target)
            media_type = "audio" if request.capability == "audio.extract" else "video"
            assets.append({"id": asset_id, "type": media_type, "name": target.name, "path": f"assets/{target.name}", "metadata": {"generatedBy": "media_processing_provider", "provider": "mediakit", "capability": request.capability, "sourceAssetId": source_asset_id, "sourcePath": record.sourcePath, "executionId": record_id, "parameters": record.parameters, "ffprobe": probe}})
            update_project(project_id, {"assets": assets})
            record = record.model_copy(update={"status": "succeeded", "outputPath": str(target.relative_to(root)), "artifactId": asset_id, "result": result | {"ffprobe": probe}})
        else:
            record = record.model_copy(update={"status": "succeeded", "result": result})
    except MediaKitError as exc:
        record = record.model_copy(update={"status": "failed", "providerError": {"message": str(exc), **exc.details}, "retryable": exc.retryable})
    record_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    return {"execution": record.model_dump(mode="json"), "recordPath": str(record_path.relative_to(root))}
