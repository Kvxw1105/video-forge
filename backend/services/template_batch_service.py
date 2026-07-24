"""Durable single-source batch orchestration for template video production."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from config import PROJECTS_DIR
from models.project import Project
from models.template_batch import BatchOutputs, TemplateBatchSpec
from services import template_service
from services.project_service import _deep_merge, _project_dir, create_project, create_project_from_payload, get_project, update_project
from shared.structured_import import parse_structured_markdown
from shared.structured_presets import build_blocks, build_default_structured_variants

MAX_ASSET_BYTES = 2 * 1024 * 1024 * 1024
_BATCH_LOCK = Lock()
_VARIABLE = re.compile(r"{{\s*([^{}]+?)\s*}}")
_SAFE_OVERRIDE_KEYS = {"canvas", "visualMode", "overlays", "audio", "timeline", "perImageDuration", "shuffleMode", "exportSettings"}
_MEDIA_EXTENSIONS = {"images": {".png", ".jpg", ".jpeg", ".webp", ".bmp"}, "videos": {".mp4", ".mov", ".mkv", ".avi", ".webm"}, "bgm": {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}}


class BatchError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _now() -> str:
    return datetime.now().isoformat()


def _hash(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _root() -> Path:
    root = PROJECTS_DIR / ".batches"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _dir(batch_id: str) -> Path:
    return _root() / batch_id


def _atomic_json(path: Path, value: dict) -> None:
    temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _event(batch_id: str, item_id: str | None, phase: str, result: str, error: str | None = None) -> None:
    # No scripts, credentials, or raw provider errors belong in the event stream.
    payload = {"at": _now(), "batchId": batch_id, "itemId": item_id, "phase": phase, "result": result}
    if error:
        payload["error"] = str(error)[:300]
    with (_dir(batch_id) / "events.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        handle.flush(); os.fsync(handle.fileno())


def _load(batch_id: str) -> tuple[dict, dict]:
    directory = _dir(batch_id)
    try:
        return json.loads((directory / "spec.json").read_text(encoding="utf-8")), json.loads((directory / "batch.json").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BatchError("batch_not_found", f"Batch not found: {batch_id}") from exc


def _save(batch_id: str, batch: dict) -> None:
    batch["updatedAt"] = _now()
    _atomic_json(_dir(batch_id) / "batch.json", batch)


def _find_idempotent(key: str) -> tuple[str, dict] | None:
    for directory in _root().iterdir():
        file = directory / "batch.json"
        if not file.is_file():
            continue
        try:
            value = json.loads(file.read_text(encoding="utf-8"))
            if value.get("idempotencyKey") == key:
                return directory.name, value
        except (OSError, json.JSONDecodeError):
            continue
    return None


def _variables(spec: TemplateBatchSpec, item, index: int) -> dict[str, str]:
    values = {"title": item.variables.get("title", item.name), "itemId": item.itemId, "index": str(index + 1), "batchName": spec.name}
    values.update({f"variables.{key}": str(value) for key, value in item.variables.items()})
    return values


def _render_variables(value, values: dict[str, str]):
    if isinstance(value, str):
        def replace(match):
            key = match.group(1)
            if key not in values:
                raise BatchError("unknown_template_variable", f"Unknown template variable: {key}")
            return values[key]
        return _VARIABLE.sub(replace, value)
    if isinstance(value, list):
        return [_render_variables(item, values) for item in value]
    if isinstance(value, dict):
        return {key: _render_variables(item, values) for key, item in value.items()}
    return value


def _validate_overrides(overrides: dict) -> None:
    illegal = set(overrides) - _SAFE_OVERRIDE_KEYS
    if illegal:
        raise BatchError("invalid_overrides", f"Unsupported override fields: {', '.join(sorted(illegal))}")
    forbidden = json.dumps(overrides, ensure_ascii=False).lower()
    if any(marker in forbidden for marker in ("apikey", "authorization", "token", "structuredcontent.alignment", "audioslice")):
        raise BatchError("invalid_overrides", "Overrides contain protected fields")
    audio = overrides.get("audio")
    if isinstance(audio, dict) and any(key in audio for key in ("apiKey", "token", "authorization")):
        raise BatchError("invalid_overrides", "Audio credentials cannot be overridden")


def _validate_assets(item) -> None:
    for kind, values in (("images", item.assets.images), ("videos", item.assets.videos), ("bgm", [item.assets.bgm] if item.assets.bgm else [])):
        for raw in values:
            path = Path(raw)
            if not path.is_file():
                raise BatchError("asset_missing", f"Missing {kind} asset: {path.name}")
            if path.suffix.lower() not in _MEDIA_EXTENSIONS[kind]:
                raise BatchError("asset_type_invalid", f"Invalid {kind} asset type: {path.suffix}")
            if path.stat().st_size > MAX_ASSET_BYTES:
                raise BatchError("asset_too_large", f"Asset exceeds size limit: {path.name}")


def _validate_item(spec: TemplateBatchSpec, item, index: int) -> list[str]:
    template_id = item.templateId or spec.templateId
    if not template_service.get_template(template_id):
        raise BatchError("template_not_found", f"Template not found: {template_id}")
    _validate_overrides(item.overrides)
    mode = spec.defaults.inputMode
    workflow = spec.visualWorkflow or {}
    if workflow.get("enabled") and workflow.get("mode") == "generation_pack" and mode != "structured_markdown":
        raise BatchError("generation_pack_requires_structured_input", "generation_pack requires structured_markdown with timestamp-aligned subtitles")
    if mode == "plain_script" and not str(item.script or "").strip():
        raise BatchError("script_required", "plain_script requires script")
    if mode == "structured_markdown":
        if not str(item.structuredMarkdown or "").strip():
            raise BatchError("structured_markdown_required", "structured_markdown requires structuredMarkdown")
        parsed = parse_structured_markdown(item.structuredMarkdown)
        if any(section.detected_type is None for section in parsed.sections):
            return ["needs_mapping"]
        if any(not section.text.strip() for section in parsed.sections):
            raise BatchError("structured_empty_section", "structured markdown contains an empty Section")
        blocks = build_blocks(list(parsed.sections))
        if not blocks or not any(str(block.get("text") or "").strip() for block in blocks):
            raise BatchError("structured_blocks_required", "structured markdown has no valid Blocks")
    _validate_assets(item)
    voice = spec.defaults.voiceover
    if mode == "structured_markdown" and voice.engine not in {"fish_audio", "none"}:
        raise BatchError("unsupported_combination", "structured_markdown supports only fish_audio or none")
    if voice.engine in {"fish_audio", "manbo", "custom"} and spec.defaults.concurrency != 1:
        raise BatchError("paid_tts_concurrency", "paid or Fish voiceover requires concurrency=1")
    return []


def plan(spec_payload: dict) -> dict:
    spec = TemplateBatchSpec.model_validate(spec_payload)
    normalized = spec.model_dump(mode="json")
    warnings, errors, items = [], [], []
    for index, item in enumerate(spec.items):
        try:
            status = "valid"; item_warnings = _validate_item(spec, item, index)
            if item_warnings:
                status = "needs_mapping"; warnings.extend(f"{item.itemId}:{warning}" for warning in item_warnings)
            items.append({"itemId": item.itemId, "status": status, "warnings": item_warnings})
        except BatchError as exc:
            errors.append({"itemId": item.itemId, "code": exc.code, "message": str(exc)})
            items.append({"itemId": item.itemId, "status": "invalid", "warnings": []})
    output = spec.defaults.outputs
    return {"valid": not errors and not warnings, "specHash": _hash(normalized), "template": {"id": spec.templateId, "name": (template_service.get_template(spec.templateId) or {}).get("name", "")}, "itemCount": len(spec.items), "estimatedActions": {"projects": len(spec.items), "assetUploads": sum(len(item.assets.images) + len(item.assets.videos) + bool(item.assets.bgm) for item in spec.items), "ttsCalls": len(spec.items) if spec.defaults.voiceover.enabled and spec.defaults.voiceover.engine != "none" else 0, "previews": len(spec.items) if output.preview else 0, "jianyingDrafts": len(spec.items) if output.jianyingDirect else 0}, "paidCallWarning": spec.defaults.voiceover.engine in {"fish_audio", "manbo", "custom"}, "items": items, "warnings": warnings, "errors": errors}


def start(spec_payload: dict, start_job) -> dict:
    result = plan(spec_payload)
    if not result["valid"]:
        raise BatchError("batch_plan_invalid", "Batch plan has validation errors or needs mapping")
    spec = TemplateBatchSpec.model_validate(spec_payload)
    normalized, spec_hash = spec.model_dump(mode="json"), result["specHash"]
    with _BATCH_LOCK:
        prior = _find_idempotent(spec.idempotencyKey)
        if prior:
            batch_id, manifest = prior
            if manifest.get("specHash") != spec_hash:
                raise BatchError("idempotency_key_conflict", "idempotencyKey was already used with a different spec")
            return {"batchId": batch_id, "jobId": manifest.get("jobId"), "status": manifest.get("status"), "idempotent": True}
        batch_id = f"batch_{uuid4().hex[:12]}"; directory = _dir(batch_id); directory.mkdir(parents=True)
        batch = _new_manifest(batch_id, spec, spec_hash)
        _atomic_json(directory / "spec.json", normalized); _save(batch_id, batch); _event(batch_id, None, "queued", "ok")
        job = start_job("template_batch", lambda update: execute(batch_id, update))
        batch["jobId"] = job["jobId"]; _save(batch_id, batch)
    return {"batchId": batch_id, "jobId": job["jobId"], "status": "queued", "idempotent": False}


def _new_manifest(batch_id: str, spec: TemplateBatchSpec, spec_hash: str) -> dict:
    now = _now()
    return {"schemaVersion": 1, "batchId": batch_id, "name": spec.name, "idempotencyKey": spec.idempotencyKey, "specHash": spec_hash, "status": "queued", "progress": 0, "totalItems": len(spec.items), "succeededItems": 0, "failedItems": 0, "skippedItems": 0, "currentItemId": None, "createdAt": now, "updatedAt": now, "items": [{"itemId": item.itemId, "status": "queued", "phase": "queued", "projectId": None, "previewUrl": None, "jianyingDraftPath": None, "jianyingZipPath": None, "duration": None, "visualPlanId": None, "generationPackPath": None, "expectedScenes": [], "visualCoverage": None, "outputs": {"preview": None, "jianying": None}, "attempts": 0, "errorCode": None, "error": None, "startedAt": None, "finishedAt": None} for item in spec.items]}


def _copy_assets(project_id: str, item) -> dict:
    directory = _project_dir(project_id); assets_dir = directory / "assets"; assets_dir.mkdir(exist_ok=True)
    copied = {"images": [], "videos": [], "bgm": None}
    for kind, values in (("images", item.assets.images), ("videos", item.assets.videos)):
        for raw in values:
            source = Path(raw); destination = assets_dir / source.name
            if destination.exists(): destination = assets_dir / f"{source.stem}_{uuid4().hex[:8]}{source.suffix}"
            shutil.copy2(source, destination); copied[kind].append((Path("assets") / destination.name).as_posix())
    if item.assets.bgm:
        source = Path(item.assets.bgm); destination = assets_dir / source.name
        if destination.exists(): destination = assets_dir / f"{source.stem}_{uuid4().hex[:8]}{source.suffix}"
        shutil.copy2(source, destination); copied["bgm"] = (Path("assets") / destination.name).as_posix()
    return copied


def _create_structured(spec: TemplateBatchSpec, item, index: int, template_id: str) -> str:
    parsed = parse_structured_markdown(item.structuredMarkdown or "")
    blocks = build_blocks(list(parsed.sections)); variants = build_default_structured_variants(blocks); variants.pop("warnings", None)
    template = template_service.get_template(template_id) or {}
    project_id = f"proj_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"; now = _now()
    base = Project(id=project_id, name=item.name, created_at=now, updated_at=now).model_dump()
    reusable = {key: template[key] for key in ("templateId", "visualMode", "canvas", "overlays", "audio", "timeline", "perImageDuration", "shuffleMode") if key in template}
    payload = _deep_merge(base, reusable); payload = _deep_merge(payload, item.overrides)
    payload.update({"id": project_id, "name": item.name, "script": "\n\n".join(block["text"] for block in blocks if block.get("enabled", True)), "structuredContent": {"schemaVersion": 1, "episode": {"episodeId": f"episode_{item.itemId}", "title": item.name, "blocks": blocks, **variants, "bindings": []}}, "created_at": now, "updated_at": now})
    return create_project_from_payload(payload).id


def _process_item(batch_id: str, spec: TemplateBatchSpec, item, index: int, result: dict) -> None:
    outputs: BatchOutputs = item.outputs or spec.defaults.outputs
    template_id = item.templateId or spec.templateId
    result.update({"status": "running", "phase": "create_project", "attempts": int(result.get("attempts") or 0) + 1, "startedAt": _now()})
    _event(batch_id, item.itemId, "create_project", "started")
    _validate_item(spec, item, index)
    if result.get("projectId") and get_project(result["projectId"]): project_id = result["projectId"]
    elif spec.defaults.inputMode == "structured_markdown": project_id = _create_structured(spec, item, index, template_id)
    else: project_id = create_project(item.name, spec.defaults.ratio, template_id).id
    result["projectId"] = project_id
    project = get_project(project_id); project_data = project.model_dump()
    project_data = _render_variables(project_data, _variables(spec, item, index)); project_data = _deep_merge(project_data, item.overrides)
    if spec.defaults.inputMode == "plain_script": project_data["script"] = item.script
    copied = _copy_assets(project_id, item)
    visual = copied["images"] + copied["videos"]
    if visual:
        project_data["assets"] = [{"id": f"asset_{i:03d}", "type": "image" if Path(path).suffix.lower() in _MEDIA_EXTENSIONS["images"] else "video", "name": Path(path).name, "path": path, "metadata": {}} for i, path in enumerate(visual, 1)]
        project_data["segments"] = [{"id": f"segment_{i:03d}", "assetPath": path, "type": "image" if Path(path).suffix.lower() in _MEDIA_EXTENSIONS["images"] else "video", "start": 0, "end": 0} for i, path in enumerate(visual, 1)]
    if copied["bgm"]: project_data.setdefault("audio", {}).setdefault("bgm", {})["file"] = copied["bgm"]
    update_project(project_id, project_data)
    voice = spec.defaults.voiceover
    if voice.enabled and voice.engine != "none":
        result["phase"] = "voiceover"; _event(batch_id, item.itemId, "voiceover", "started")
        if voice.engine == "fish_audio":
            from routers.structured_audio import generate_fish_aligned
            generate_fish_aligned(project_id, {"referenceId": "", "generateSubtitles": voice.generateSubtitles})
        else:
            from routers.voiceover import generate
            generate(project_id, {"text": item.script or "", "engine": voice.engine, "speed": voice.speed})
    from services import agent_factory_service
    stage = agent_factory_service.prepare_item_visual_stage(batch_id, spec, item, result)
    result.update(stage.patch)
    if stage.outcome == "awaiting_visual_assets":
        result.update({"status":"awaiting_visual_assets","phase":"awaiting_visual_assets","finishedAt":None})
        _event(batch_id,item.itemId,"awaiting_visual_assets","paused")
        return
    _run_item_outputs(batch_id, item.itemId, project_id, outputs, result)
    result.update({"status": "succeeded", "phase": "done", "finishedAt": _now()}); _event(batch_id, item.itemId, "done", "ok")


def _run_item_outputs(
    batch_id: str,
    item_id: str,
    project_id: str,
    outputs: BatchOutputs,
    result: dict,
    *,
    structured_variant_id: str | None = None,
    input_hash: str | None = None,
) -> None:
    """Create only the outputs that are not already retained on ``result``.

    Factory resume supplies a structured variant and an input hash.  The generic
    batch path deliberately keeps its existing behavior.
    """
    if os.environ.get("VIDEOFORGE_LAB_OUTPUT_STUB") == "1":
        root = _dir(batch_id) / "lab-output" / item_id
        root.mkdir(parents=True, exist_ok=True)
        if outputs.preview and not result.get("previewUrl"):
            preview_path = root / "preview.mp4"
            preview_path.write_bytes(b"VideoForge Lab preview stub")
            result["previewUrl"] = f"/api/agent-factory/batches/{batch_id}/items/{item_id}/preview"
            result.setdefault("outputs", {})["preview"] = {"status": "succeeded", "url": result["previewUrl"], "path": str(preview_path), "inputHash": input_hash, "completedAt": _now()}
        if outputs.jianyingDirect and not result.get("jianyingDraftPath"):
            draft = root / "jianying-draft"
            draft.mkdir(exist_ok=True)
            (draft / "draft_content.json").write_text("{}", encoding="utf-8")
            result["jianyingDraftPath"] = str(draft)
            result.setdefault("outputs", {})["jianying"] = {"status": "succeeded", "draftPath": result["jianyingDraftPath"], "inputHash": input_hash, "completedAt": _now()}
        return
    if outputs.preview and not result.get("previewUrl"):
        result["phase"]="rendering_preview"; _event(batch_id,item_id,"rendering_preview","started")
        if structured_variant_id:
            from routers.render import generate_structured_variant_preview
            preview = generate_structured_variant_preview(project_id, structured_variant_id)
            preview_path = _project_dir(project_id) / f"preview_{structured_variant_id}.mp4"
        else:
            from routers.render import generate_preview
            preview = generate_preview(project_id)
            preview_path = preview.get("previewPath") or _project_dir(project_id) / "preview.mp4"
        result["previewUrl"] = preview.get("previewUrl")
        result["duration"] = preview.get("duration")
        result.setdefault("outputs", {})["preview"] = {
            "status": "succeeded", "url": result["previewUrl"],
            "path": str(preview_path), "inputHash": input_hash,
            "completedAt": _now(),
        }
    if outputs.jianyingDirect and not result.get("jianyingDraftPath"):
        result["phase"]="exporting_jianying"; _event(batch_id,item_id,"exporting_jianying","started")
        if structured_variant_id:
            from routers.export import export_structured_variant_direct
            exported = export_structured_variant_direct(project_id, structured_variant_id, policy="create_new")
        else:
            from routers.export import export_jianying_direct
            exported = export_jianying_direct(project_id, policy="create_new")
        result["jianyingDraftPath"] = exported.get("finalPath") or exported.get("path")
        result.setdefault("outputs", {})["jianying"] = {
            "status": "succeeded", "draftPath": result["jianyingDraftPath"],
            "inputHash": input_hash, "completedAt": _now(),
        }


def _aggregate_batch_status(items: list[dict]) -> str:
    states=[item.get("status") for item in items]
    if "running" in states: return "running"
    if "awaiting_visual_assets" in states: return "awaiting_visual_assets"
    if "ready_to_resume" in states: return "ready_to_resume"
    if states and all(state=="succeeded" for state in states): return "succeeded"
    if "failed" in states and "succeeded" in states: return "partial"
    if states and all(state=="failed" for state in states): return "failed"
    return "queued"


def execute(batch_id: str, update=lambda *_: None) -> dict:
    spec_payload, batch = _load(batch_id); spec = TemplateBatchSpec.model_validate(spec_payload)
    batch["status"] = "running"; _save(batch_id, batch)
    for index, item in enumerate(spec.items):
        result = batch["items"][index]
        if result["status"] == "succeeded":
            batch["skippedItems"] += 1; continue
        batch["currentItemId"] = item.itemId; _save(batch_id, batch)
        try:
            _process_item(batch_id, spec, item, index, result)
        except Exception as exc:
            code = getattr(exc, "code", "item_failed")
            result.update({"status": "failed", "phase": "failed", "errorCode": code, "error": str(exc)[:500], "finishedAt": _now()}); _event(batch_id, item.itemId, "failed", "failed", str(exc))
            if not spec.defaults.continueOnError: break
        finally:
            total = len(spec.items); done = sum(1 for row in batch["items"] if row["status"] in {"succeeded", "failed", "awaiting_visual_assets", "ready_to_resume"})
            batch["succeededItems"] = sum(1 for row in batch["items"] if row["status"] == "succeeded"); batch["failedItems"] = sum(1 for row in batch["items"] if row["status"] == "failed"); batch["progress"] = int(done * 100 / total); update(batch["progress"], "batch", item.itemId); _save(batch_id, batch)
    batch["currentItemId"] = None
    batch["status"] = _aggregate_batch_status(batch["items"])
    _save(batch_id, batch); return batch


def resume(batch_id: str, start_job) -> dict:
    _, batch = _load(batch_id)
    if batch.get("status") == "succeeded": return {"batchId": batch_id, "jobId": batch.get("jobId"), "status": "succeeded", "idempotent": True}
    for item in batch["items"]:
        if item["status"] == "running": item.update({"status": "interrupted", "phase": "interrupted", "finishedAt": _now()})
        if item["status"] in {"failed", "interrupted"}: item.update({"status": "queued", "phase": "queued", "error": None, "errorCode": None})
    batch["status"] = "queued"; _save(batch_id, batch)
    job = start_job("template_batch", lambda update: execute(batch_id, update)); batch["jobId"] = job["jobId"]; _save(batch_id, batch)
    return {"batchId": batch_id, "jobId": job["jobId"], "status": "queued"}


def get(batch_id: str) -> dict: return _load(batch_id)[1]
def manifest(batch_id: str) -> dict: return {"spec": _load(batch_id)[0], "batch": _load(batch_id)[1], "path": str(_dir(batch_id))}
def list_batches() -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(_root().glob("*/batch.json"), key=lambda value: value.stat().st_mtime_ns, reverse=True)]
