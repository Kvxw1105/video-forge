from __future__ import annotations

import hashlib
import base64
import binascii
import ipaddress
import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from urllib.parse import urlparse

import httpx

from config import CONFIG_DIR
from models.image_generation import ImageGenerationBatch, ImageProviderSettings
from services.project_service import _project_dir, get_project, update_project
from shared.visual_scene import visual_source_hash
from visual_providers import get_provider
from visual_providers.contracts import SceneRequest
from visual_providers.router import route_scene


class ImageGenerationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_SETTINGS_FILE = CONFIG_DIR / "ai_image_provider.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _batch_dir(project_id: str) -> Path:
    return _project_dir(project_id) / "image-generation" / "batches"


def _batch_path(project_id: str, batch_id: str) -> Path:
    if not batch_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in batch_id):
        raise ImageGenerationError("invalid_batch_id", "Invalid image generation batch ID")
    return _batch_dir(project_id) / f"{batch_id}.json"


def _write_batch(batch: dict) -> dict:
    validated = ImageGenerationBatch.model_validate(batch)
    target = _batch_path(validated.projectId, validated.batchId)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f".json.tmp-{uuid4().hex}")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(validated.model_dump_json(indent=2))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return validated.model_dump(mode="json")


def load_image_provider_settings() -> ImageProviderSettings:
    if not _SETTINGS_FILE.is_file():
        return ImageProviderSettings()
    try:
        return ImageProviderSettings.model_validate_json(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ImageProviderSettings()


def save_image_provider_settings(settings: ImageProviderSettings) -> None:
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = _SETTINGS_FILE.with_suffix(f".json.tmp-{uuid4().hex}")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(settings.model_dump_json(indent=2))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, _SETTINGS_FILE)
    finally:
        if temporary.exists():
            temporary.unlink()


def public_image_provider_settings(settings: ImageProviderSettings) -> dict:
    data = settings.model_dump(mode="json")
    data["apiKeyConfigured"] = bool(data["apiKey"])
    data["apiKey"] = ""
    return data


def update_image_provider_settings(payload: dict) -> dict:
    current = load_image_provider_settings()
    allowed = set(ImageProviderSettings.model_fields)
    updates = {key: value for key, value in payload.items() if key in allowed}
    if not str(updates.get("apiKey") or "").strip():
        updates.pop("apiKey", None)
    settings = ImageProviderSettings.model_validate({**current.model_dump(), **updates})
    save_image_provider_settings(settings)
    return public_image_provider_settings(settings)


def _provider_headers(settings: ImageProviderSettings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.apiKey}",
        "Content-Type": "application/json",
    }


def _provider_url(settings: ImageProviderSettings, suffix: str) -> str:
    base = settings.baseUrl.strip().rstrip("/")
    if not base:
        raise ImageGenerationError("provider_not_configured", "AI image provider Base URL is missing")
    return f"{base}/{suffix.lstrip('/')}"


def fetch_image_provider_models(settings: ImageProviderSettings | None = None) -> dict:
    settings = settings or load_image_provider_settings()
    if not settings.apiKey:
        raise ImageGenerationError("provider_not_configured", "AI image provider API Key is missing")
    try:
        response = httpx.get(
            _provider_url(settings, "models"),
            headers=_provider_headers(settings),
            timeout=settings.timeoutSeconds,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ImageGenerationError("provider_connection_failed", f"AI image provider connection failed: {exc}") from exc
    models = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        models = []
    return {"ok": True, "models": models, "message": f"Discovered {len(models)} model(s)"}


def get_batch(project_id: str, batch_id: str) -> dict:
    target = _batch_path(project_id, batch_id)
    if not target.is_file():
        raise ImageGenerationError("batch_not_found", f"Image generation batch not found: {batch_id}")
    try:
        return ImageGenerationBatch.model_validate_json(target.read_text(encoding="utf-8")).model_dump(mode="json")
    except (OSError, ValueError) as exc:
        raise ImageGenerationError("batch_invalid", f"Image generation batch is unreadable: {batch_id}") from exc


def _find_item(batch: dict, scene_id: str) -> dict:
    item = next((value for value in batch["items"] if value["sceneId"] == scene_id), None)
    if item is None:
        raise ImageGenerationError("scene_not_found", f"Scene is not part of this batch: {scene_id}")
    return item


def _ensure_current(batch: dict):
    project = get_project(batch["projectId"])
    episode = project.structuredContent.episode if project and project.structuredContent else None
    plan = episode.visualPlan if episode else None
    current_hash = visual_source_hash(project.model_dump()) if project else ""
    if (
        plan is None
        or plan.planId != batch["visualPlanId"]
        or plan.sourceHash != batch["visualSourceHash"]
        or current_hash != batch["visualSourceHash"]
    ):
        batch["status"] = "stale"
        batch["updatedAt"] = _now()
        _write_batch(batch)
        raise ImageGenerationError(
            "visual_plan_stale", "The image generation batch is stale for the current VisualPlan"
        )
    return project, plan


def ensure_batch_current(batch: dict) -> dict:
    _ensure_current(batch)
    return batch


def _aggregate_status(batch: dict) -> str:
    statuses = [item["status"] for item in batch["items"]]
    if statuses and all(status == "bound" for status in statuses):
        return "succeeded"
    if statuses and all(status == "failed" for status in statuses):
        return "failed"
    if any(status == "generating" for status in statuses):
        return "running"
    if any(status == "failed" for status in statuses):
        return "partial"
    if any(status == "pending" for status in statuses):
        return "awaiting_agent" if batch["channel"] == "agent" else "pending"
    if any(status in {"generated", "approved"} for status in statuses):
        return "awaiting_approval"
    return batch.get("status") or "pending"


def _save_changed(batch: dict) -> dict:
    batch["status"] = _aggregate_status(batch)
    batch["updatedAt"] = _now()
    return _write_batch(batch)


def _media_type(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp", "image/webp"
    if data.startswith(b"\x00\x00\x00") and b"ftyp" in data[:32]:
        return ".mp4", "video/mp4"
    raise ImageGenerationError("media_type_unsupported", "Only PNG, JPEG, WebP, and MP4 media are supported")


_image_type = _media_type


def _read_image_source(source: Path | bytes) -> bytes:
    if isinstance(source, bytes):
        data = source
    else:
        try:
            data = Path(source).read_bytes()
        except OSError as exc:
            raise ImageGenerationError("image_read_failed", f"Unable to read generated image: {source}") from exc
    if not data:
        raise ImageGenerationError("image_empty", "Generated image is empty")
    if len(data) > 20 * 1024 * 1024:
        raise ImageGenerationError("image_too_large", "Generated image exceeds the 20 MB limit")
    return data


def _candidate_from_bytes(
    batch: dict,
    item: dict,
    data: bytes,
    *,
    revised_prompt: str = "",
    metadata: dict | None = None,
    media_type: str = "",
    filename: str = "",
) -> dict:
    if not data:
        raise ImageGenerationError("image_empty", "Generated image is empty")
    settings = load_image_provider_settings()
    if len(data) > settings.maxDownloadBytes:
        raise ImageGenerationError(
            "image_too_large",
            f"Generated image exceeds the {settings.maxDownloadBytes} byte limit",
        )
    suffix, detected_type = _media_type(data)
    mime_type = media_type or detected_type
    if mime_type not in {"image/png", "image/jpeg", "image/webp", "video/mp4"}:
        raise ImageGenerationError("media_type_unsupported", f"Unsupported provider media type: {mime_type}")
    content_hash = hashlib.sha256(data).hexdigest()
    existing = next(
        (candidate for candidate in item["candidates"] if candidate["contentHash"] == content_hash),
        None,
    )
    if existing:
        return existing
    candidate_id = f"candidate_{item['sceneId']}_{content_hash[:12]}"
    relative = (
        Path("image-generation")
        / "candidates"
        / batch["batchId"]
        / f"{candidate_id}{Path(filename).suffix.lower() if filename and Path(filename).suffix else suffix}"
    )
    target = _project_dir(batch["projectId"]) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f"{target.suffix}.tmp-{uuid4().hex}")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            temporary.write_bytes(data)
            os.replace(temporary, target)
        except FileNotFoundError:
            # Windows may transiently invalidate a temp path under an indexed
            # test/storage directory; retry once with a fresh destination.
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    finally:
        if temporary.exists():
            temporary.unlink()
    candidate = {
        "candidateId": candidate_id,
        "path": relative.as_posix(),
        "contentHash": content_hash,
        "mimeType": mime_type,
        "status": "generated",
        "revisedPrompt": revised_prompt,
        "createdAt": _now(),
        "metadata": dict(metadata or {}),
    }
    item["candidates"].append(candidate)
    return candidate


def _parse_size(value: str, aspect_ratio: str) -> tuple[int, int]:
    try:
        width, height = (int(part) for part in str(value or "").lower().split("x", 1))
        if width > 0 and height > 0:
            return width, height
    except (TypeError, ValueError):
        pass
    fallback = _default_size(aspect_ratio)
    width, height = (int(part) for part in fallback.split("x", 1))
    return width, height


def _write_provider_sidecars(project_id: str, candidate: dict, sidecars: dict[str, bytes]) -> dict:
    if not sidecars:
        return candidate
    candidate_path = _project_dir(project_id) / candidate["path"]
    stored = []
    for name, data in sidecars.items():
        safe_name = Path(str(name)).name
        if not safe_name:
            continue
        target = candidate_path.with_name(f"{candidate_path.stem}.{safe_name}")
        temporary = target.with_suffix(f"{target.suffix}.tmp-{uuid4().hex}")
        try:
            temporary.write_bytes(data)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        stored.append((target.relative_to(_project_dir(project_id))).as_posix())
    candidate.setdefault("metadata", {})["sidecars"] = stored
    return candidate


def upload_agent_candidate(
    project_id: str,
    batch_id: str,
    scene_id: str,
    input_hash: str,
    source: Path | bytes,
    *,
    revised_prompt: str = "",
) -> dict:
    batch = get_batch(project_id, batch_id)
    _ensure_current(batch)
    if batch["channel"] != "agent":
        raise ImageGenerationError("channel_mismatch", "Agent upload requires an Agent image batch")
    item = _find_item(batch, scene_id)
    if input_hash != item["inputHash"]:
        raise ImageGenerationError("input_stale", f"Agent image input is stale for Scene {scene_id}")
    data = _read_image_source(source)
    candidate = _candidate_from_bytes(batch, item, data, revised_prompt=revised_prompt)
    item["status"] = "generated"
    item["errorCode"] = ""
    item["error"] = ""
    _save_changed(batch)
    return candidate


def _safe_remote_image_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ImageGenerationError("provider_image_url_invalid", "Provider returned an invalid image URL")
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ImageGenerationError("provider_image_url_blocked", "Provider returned a blocked local image URL")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved):
        raise ImageGenerationError("provider_image_url_blocked", "Provider returned a blocked private image URL")
    return value


def _download_provider_image(url: str, settings: ImageProviderSettings) -> bytes:
    try:
        response = httpx.get(
            _safe_remote_image_url(url),
            timeout=settings.timeoutSeconds,
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ImageGenerationError("provider_image_download_failed", f"Unable to download provider image: {exc}") from exc
    content_type = str(response.headers.get("content-type") or "").split(";", 1)[0].lower()
    if content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise ImageGenerationError("provider_image_type_invalid", "Provider URL did not return a supported image")
    data = response.content
    if len(data) > settings.maxDownloadBytes:
        raise ImageGenerationError("image_too_large", "Provider image exceeds the configured download limit")
    _image_type(data)
    return data


def _generate_provider_images(
    settings: ImageProviderSettings,
    item: dict,
    model: str,
    candidate_count: int,
) -> list[tuple[bytes, str]]:
    prompt = item["finalPrompt"]
    if item.get("negativePrompt"):
        prompt = f"{prompt}\nAvoid: {item['negativePrompt']}"
    try:
        response = httpx.post(
            _provider_url(settings, "images/generations"),
            headers=_provider_headers(settings),
            json={
                "model": model,
                "prompt": prompt,
                "n": candidate_count,
                "size": item["size"],
                "response_format": "b64_json",
            },
            timeout=settings.timeoutSeconds,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ImageGenerationError("provider_generation_failed", f"AI image provider failed: {exc}") from exc
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ImageGenerationError("provider_response_invalid", "AI image provider returned no images")
    generated = []
    for row in rows[:candidate_count]:
        if not isinstance(row, dict):
            continue
        revised = str(row.get("revised_prompt") or "")
        if row.get("b64_json"):
            try:
                data = base64.b64decode(str(row["b64_json"]), validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ImageGenerationError("provider_response_invalid", "Provider returned invalid base64 image data") from exc
        elif row.get("url"):
            data = _download_provider_image(str(row["url"]), settings)
        else:
            continue
        _image_type(data)
        generated.append((data, revised))
    if not generated:
        raise ImageGenerationError("provider_response_invalid", "AI image provider returned no usable images")
    return generated


def run_builtin_batch(project_id: str, batch_id: str, update=None) -> dict:
    batch = get_batch(project_id, batch_id)
    _ensure_current(batch)
    if batch["channel"] != "builtin":
        raise ImageGenerationError("channel_mismatch", "Only a built-in image batch can call the configured provider")
    settings = load_image_provider_settings()
    if not settings.enabled or not settings.apiKey or not settings.baseUrl:
        raise ImageGenerationError("provider_not_configured", "AI image provider is not fully configured")
    model = batch.get("model") or settings.model
    if not model:
        raise ImageGenerationError("provider_not_configured", "AI image provider model is missing")
    pending = [item for item in batch["items"] if item["status"] in {"pending", "failed"}]
    if not pending:
        return batch
    for item in pending:
        item["status"] = "generating"
        item["attempts"] = int(item.get("attempts") or 0) + 1
        item["errorCode"] = ""
        item["error"] = ""
    batch["status"] = "running"
    batch["updatedAt"] = _now()
    _write_batch(batch)
    completed = 0
    with ThreadPoolExecutor(max_workers=settings.maxConcurrency) as executor:
        futures = {
            executor.submit(
                _generate_provider_images,
                settings,
                item,
                model,
                int(batch["candidateCount"]),
            ): item
            for item in pending
        }
        for future in as_completed(futures):
            item = futures[future]
            try:
                for data, revised_prompt in future.result():
                    _candidate_from_bytes(batch, item, data, revised_prompt=revised_prompt)
                item["status"] = "generated"
            except Exception as exc:
                item["status"] = "failed"
                item["errorCode"] = getattr(exc, "code", "provider_generation_failed")
                item["error"] = str(exc)[:1000]
            completed += 1
            _save_changed(batch)
            if update:
                update(
                    completed / len(pending) * 100,
                    "generating_images",
                    f"Generated {completed}/{len(pending)} Scene request(s)",
                )
    saved = get_batch(project_id, batch_id)
    selections = [
        {"sceneId": item["sceneId"], "candidateId": item["candidates"][0]["candidateId"]}
        for item in saved["items"]
        if item["status"] == "generated" and item["candidates"]
    ]
    if saved.get("autoApprove") and selections:
        return approve_candidates(project_id, batch_id, selections)["batch"]
    return saved


def run_local_batch(project_id: str, batch_id: str, update=None) -> dict:
    batch = get_batch(project_id, batch_id)
    _ensure_current(batch)
    if batch["channel"] != "local":
        raise ImageGenerationError("channel_mismatch", "Only local visual-provider batches can run locally")
    pending = [item for item in batch["items"] if item["status"] in {"pending", "failed"}]
    if not pending:
        return batch
    for item in pending:
        item["status"] = "generating"
        item["attempts"] = int(item.get("attempts") or 0) + 1
        item["errorCode"] = ""
        item["error"] = ""
    batch["status"] = "running"
    batch["updatedAt"] = _now()
    _write_batch(batch)
    completed = 0
    for item in pending:
        try:
            provider_id = item.get("providerId") or batch.get("providerId") or "stickman"
            try:
                provider = get_provider(provider_id)
            except KeyError as exc:
                raise ImageGenerationError("provider_not_found", f"Local visual provider is not registered: {provider_id}") from exc
            width, height = _parse_size(item.get("size"), item.get("aspectRatio") or "9:16")
            for candidate_index in range(max(1, int(batch.get("candidateCount") or 1))):
                result = provider.generate(SceneRequest(
                    project_id=project_id,
                    visual_plan_id=batch["visualPlanId"],
                    scene_id=item["sceneId"],
                    block_id=item.get("blockId") or "",
                    subtitle_ids=tuple(item.get("subtitleIds") or ()),
                    text=item.get("text") or "",
                    start=float(item["start"]),
                    end=float(item["end"]),
                    duration=float(item["duration"]),
                    input_hash=item["inputHash"],
                    aspect_ratio=item.get("aspectRatio") or "9:16",
                    width=width,
                    height=height,
                    options={
                        "finalPrompt": item.get("finalPrompt") or "",
                        "styleAnchor": item.get("styleAnchor") or "",
                        "continuityAnchor": item.get("continuityAnchor") or "",
                        "negativePrompt": item.get("negativePrompt") or "",
                        "candidateIndex": candidate_index,
                        "requestedMediaType": item.get("requestedMediaType") or "image",
                        "outputMode": item.get("outputMode") or ("video" if provider_id == "code_visual" and item.get("durationPolicy") == "exact" and item.get("renderMode") == "video" else "static"),
                        "durationPolicy": item.get("durationPolicy") or "exact",
                        "semanticIntent": item.get("sceneIntent") or "",
                        "routeHints": item.get("routeHints") or {},
                    },
                ))
                if not result.success:
                    raise ImageGenerationError(result.error_code or "provider_generation_failed", result.error or "Local provider failed")
                if result.input_hash != item["inputHash"]:
                    raise ImageGenerationError("provider_input_mismatch", "Local provider returned a mismatched input hash")
                if result.asset_kind == "video":
                    provider_duration = float(result.duration or 0)
                    scene_duration = float(item["duration"])
                    duration_policy = str(item.get("durationPolicy") or result.duration_policy or "exact")
                    if provider_duration <= 0:
                        raise ImageGenerationError("provider_duration_missing", "Dynamic provider did not return a duration")
                    if duration_policy == "reject" and abs(provider_duration - scene_duration) > 0.05:
                        raise ImageGenerationError("duration_policy_rejected", "Provider media duration does not match the Scene")
                    if duration_policy == "exact" and abs(provider_duration - scene_duration) > 0.05:
                        raise ImageGenerationError("duration_policy_exact_mismatch", "Provider media duration does not match exact Scene timing")
                candidate = _candidate_from_bytes(
                    batch,
                    item,
                    result.data,
                    metadata={
                        "providerId": result.provider_id,
                        "providerVersion": result.provider_version,
                        "duration": result.duration,
                        "durationPolicy": result.duration_policy,
                        "assetKind": result.asset_kind,
                        **result.metadata,
                    },
                    media_type=result.media_type,
                    filename=result.filename,
                )
                _write_provider_sidecars(project_id, candidate, result.sidecars)
            item["status"] = "generated"
        except Exception as exc:
            item["status"] = "failed"
            item["errorCode"] = getattr(exc, "code", "provider_generation_failed")
            item["error"] = str(exc)[:1000]
        completed += 1
        _save_changed(batch)
        if update:
            update(completed / len(pending) * 100, "generating_local_visuals", f"Generated {completed}/{len(pending)} Scene request(s)")
    saved = get_batch(project_id, batch_id)
    selections = [
        {"sceneId": item["sceneId"], "candidateId": item["candidates"][0]["candidateId"]}
        for item in saved["items"] if item["status"] == "generated" and item["candidates"]
    ]
    if saved.get("autoApprove") and selections:
        return approve_candidates(project_id, batch_id, selections)["batch"]
    return saved


def record_item_failure(
    project_id: str, batch_id: str, scene_id: str, error_code: str, message: str
) -> dict:
    batch = get_batch(project_id, batch_id)
    _ensure_current(batch)
    item = _find_item(batch, scene_id)
    item["status"] = "failed"
    item["errorCode"] = str(error_code or "generation_failed")[:128]
    item["error"] = str(message or "Image generation failed")[:1000]
    return _save_changed(batch)


def retry_failed_items(project_id: str, batch_id: str) -> dict:
    batch = get_batch(project_id, batch_id)
    _ensure_current(batch)
    changed = False
    for item in batch["items"]:
        if item["status"] != "failed":
            continue
        item["status"] = "pending"
        item["errorCode"] = ""
        item["error"] = ""
        changed = True
    if not changed:
        raise ImageGenerationError("nothing_to_retry", "The image batch has no failed items")
    return _save_changed(batch)


def approve_candidates(project_id: str, batch_id: str, selections: list[dict]) -> dict:
    batch = get_batch(project_id, batch_id)
    project, plan = _ensure_current(batch)
    if not selections:
        raise ImageGenerationError("selection_empty", "Select at least one generated image")
    scene_by_id = {scene.id: scene.model_dump() for scene in plan.scenes}
    assets = [asset.model_dump() for asset in project.assets]
    bound = []
    selected_candidates = []
    for selection in selections:
        scene_id = str(selection.get("sceneId") or "")
        candidate_id = str(selection.get("candidateId") or "")
        item = _find_item(batch, scene_id)
        scene = scene_by_id.get(scene_id)
        if scene is None:
            raise ImageGenerationError("scene_not_found", f"VisualPlan Scene not found: {scene_id}")
        candidate = next(
            (value for value in item["candidates"] if value["candidateId"] == candidate_id),
            None,
        )
        if candidate is None:
            raise ImageGenerationError("candidate_not_found", f"Candidate not found: {candidate_id}")
        source = _project_dir(project_id) / candidate["path"]
        if not source.is_file():
            raise ImageGenerationError("candidate_file_missing", f"Candidate image is missing: {candidate_id}")
        selected_candidates.append((item, scene, candidate, source))

    asset_dir = _project_dir(project_id) / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    for item, scene, candidate, source in selected_candidates:
        suffix = source.suffix.lower()
        item_provider = str(item.get("providerId") or batch.get("providerId") or "ai_image").replace("-", "_")
        asset_id = (
            f"visual_{item_provider}_{item['sceneId']}"
            if batch["channel"] == "local"
            else f"visual_ai_image_{item['sceneId']}"
        )
        filename = f"{item_provider if batch['channel'] == 'local' else 'ai'}_{item['sceneId']}_{candidate['contentHash'][:12]}{suffix}"
        destination = asset_dir / filename
        if not destination.exists():
            temporary = destination.with_suffix(f"{destination.suffix}.tmp-{uuid4().hex}")
            try:
                shutil.copy2(source, temporary)
                os.replace(temporary, destination)
            finally:
                if temporary.exists():
                    temporary.unlink()
        assets = [asset for asset in assets if asset["id"] != asset_id]
        assets.append(
            {
                "id": asset_id,
                "type": "video" if candidate.get("mimeType") == "video/mp4" else "image",
                "name": filename,
                "path": (Path("assets") / filename).as_posix(),
                "metadata": {
                    "generatedBy": "visual_provider" if batch["channel"] == "local" else "ai_image",
                    "channel": batch["channel"],
                    "provider": item.get("providerId") or batch["providerId"],
                    "model": batch["model"],
                    "batchId": batch["batchId"],
                    "sceneId": item["sceneId"],
                    "inputHash": item["inputHash"],
                    "prompt": item["finalPrompt"],
                    "negativePrompt": item["negativePrompt"],
                    "candidateId": candidate["candidateId"],
                    "providerVersion": (candidate.get("metadata") or {}).get("providerVersion", ""),
                    "sidecars": (candidate.get("metadata") or {}).get("sidecars", []),
                    "routingReason": item.get("routingReason", ""),
                    "routingConfidence": item.get("routingConfidence", 0.0),
                    "durationPolicy": item.get("durationPolicy", "exact"),
                    "assetKind": (candidate.get("metadata") or {}).get("assetKind", "image"),
                    "duration": (candidate.get("metadata") or {}).get("duration"),
                },
            }
        )
        # A Scene has one current visual binding. Re-generation replaces the
        # previous provider asset instead of accumulating stale bindings.
        scene["visualAssetIds"] = [asset_id]
        scene["primaryAssetId"] = asset_id
        candidate["status"] = "approved"
        item["status"] = "bound"
        bound.append({"sceneId": item["sceneId"], "assetId": asset_id})

    plan_data = plan.model_dump()
    plan_data["scenes"] = [scene_by_id[scene.id] for scene in plan.scenes]
    update_project(
        project_id,
        {
            "assets": assets,
            "structuredContent": {
                **project.structuredContent.model_dump(),
                "episode": {
                    **project.structuredContent.episode.model_dump(),
                    "visualPlan": plan_data,
                },
            },
        },
    )
    saved = _save_changed(batch)
    return {"bound": bound, "batch": saved}


def _default_size(aspect_ratio: str) -> str:
    if aspect_ratio in {"9:16", "4:5"}:
        return "1024x1536"
    if aspect_ratio in {"16:9", "4:3"}:
        return "1536x1024"
    return "1024x1024"


def _final_prompt(values: dict) -> str:
    sections = [
        values.get("prompt") or values.get("sceneIntent") or values.get("text"),
        f"Subject: {values['subject']}" if values.get("subject") else "",
        f"Composition: {values['composition']}" if values.get("composition") else "",
        f"Visual style: {values['styleAnchor']}" if values.get("styleAnchor") else "",
        f"Continuity: {values['continuityAnchor']}" if values.get("continuityAnchor") else "",
        f"Framing: {values['safeArea']}" if values.get("safeArea") else "",
    ]
    return "\n".join(section.strip() for section in sections if str(section or "").strip())


def create_batch(
    project_id: str,
    *,
    channel: str = "agent",
    provider_id: str = "",
    model: str = "",
    size: str = "",
    candidate_count: int = 1,
    routing_mode: str = "auto",
    auto_approve: bool = False,
    style_anchor: str = "",
    continuity_anchor: str = "",
    scene_ids: list[str] | None = None,
    scene_overrides: dict[str, dict] | None = None,
) -> dict:
    project = get_project(project_id)
    if project is None:
        raise ImageGenerationError("project_not_found", f"Project not found: {project_id}")
    episode = project.structuredContent.episode if project.structuredContent else None
    plan = episode.visualPlan if episode else None
    if plan is None:
        raise ImageGenerationError("visual_plan_missing", "A timed VisualPlan is required before image generation")
    current_source_hash = visual_source_hash(project.model_dump())
    if plan.sourceHash != current_source_hash:
        raise ImageGenerationError("visual_plan_stale", "The VisualPlan is stale; regenerate it before image generation")
    if channel not in {"builtin", "agent", "local"}:
        raise ImageGenerationError("invalid_channel", f"Unsupported image generation channel: {channel}")
    if routing_mode not in {"auto", "stickman", "code_visual"}:
        raise ImageGenerationError("invalid_routing_mode", f"Unsupported visual routing mode: {routing_mode}")
    if not 1 <= int(candidate_count) <= 4:
        raise ImageGenerationError("invalid_candidate_count", "candidate_count must be between 1 and 4")
    if channel == "builtin":
        provider_settings = load_image_provider_settings()
        provider_id = provider_id or provider_settings.providerId
        model = model or provider_settings.model
        size = size or _default_size(project.canvas.ratio)
    elif channel == "local":
        provider_id = provider_id or ("auto" if routing_mode == "auto" else routing_mode)
        size = size or _default_size(project.canvas.ratio)

    selected = set(scene_ids or [])
    unknown = selected - {scene.id for scene in plan.scenes}
    if unknown:
        raise ImageGenerationError("scene_not_found", f"Unknown VisualPlan Scenes: {', '.join(sorted(unknown))}")
    subtitle_by_id = {subtitle.id: subtitle for subtitle in project.subtitles}
    block_by_id = {block.id: block for block in episode.blocks}
    overrides = scene_overrides or {}
    batch_id = f"image_batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    items = []
    for index, scene in enumerate(plan.scenes, 1):
        if selected and scene.id not in selected:
            continue
        subtitles = [subtitle_by_id[item] for item in scene.subtitleIds if item in subtitle_by_id]
        if len(subtitles) != len(scene.subtitleIds):
            raise ImageGenerationError("scene_timing_invalid", f"Scene {scene.id} references missing subtitles")
        start = min(float(item.start) for item in subtitles)
        end = max(float(item.end) for item in subtitles)
        if end <= start:
            raise ImageGenerationError("scene_timing_invalid", f"Scene {scene.id} has an invalid time window")
        override = overrides.get(scene.id) or {}
        text = "".join(item.text for item in subtitles)
        aspect_ratio = project.canvas.ratio
        item_size = str(override.get("size") or size or _default_size(aspect_ratio))
        values = {
            "sceneIntent": str(override.get("sceneIntent") or scene.summary or text),
            "subject": str(override.get("subject") or ""),
            "composition": str(override.get("composition") or ""),
            "styleAnchor": str(override.get("styleAnchor") or style_anchor),
            "continuityAnchor": str(override.get("continuityAnchor") or continuity_anchor),
            "safeArea": str(override.get("safeArea") or f"{aspect_ratio} frame, keep the lower subtitle-safe area uncluttered"),
            "prompt": str(override.get("prompt") or scene.prompt or scene.summary or text),
        }
        final_prompt = _final_prompt({**values, "text": text})
        if not final_prompt:
            raise ImageGenerationError("prompt_missing", f"Scene {scene.id} has no image Prompt")
        negative_prompt = str(override.get("negativePrompt") or scene.negativePrompt or "text, watermark, logo")
        route_request = SceneRequest(
            project_id=project.id,
            visual_plan_id=plan.planId,
            scene_id=scene.id,
            block_id=scene.blockId,
            subtitle_ids=tuple(scene.subtitleIds),
            text=text,
            start=start,
            end=end,
            duration=end - start,
            input_hash="0" * 64,
            aspect_ratio=aspect_ratio,
            width=_parse_size(item_size, aspect_ratio)[0],
            height=_parse_size(item_size, aspect_ratio)[1],
            options={
                "finalPrompt": final_prompt,
                "requestedMediaType": scene.requestedMediaType,
                "semanticIntent": str(override.get("semanticIntent") or scene.summary or ""),
                "routeHints": dict((scene.metadata or {}).get("semantic") or {}),
            },
        )
        override_provider = str(override.get("providerId") or "")
        route = route_scene(route_request, routing_mode, override_provider)
        item_provider = route.provider_id if channel == "local" else provider_id
        item_provider_version = ""
        if channel == "local":
            try:
                item_provider_version = get_provider(item_provider).provider_version
            except KeyError as exc:
                raise ImageGenerationError("provider_not_found", f"Local visual provider is not registered: {item_provider}") from exc
        duration_policy = str(override.get("durationPolicy") or "exact")
        if duration_policy not in {"exact", "crop", "loop", "speed_adjust", "reject"}:
            raise ImageGenerationError("invalid_duration_policy", f"Unsupported duration policy: {duration_policy}")
        output_mode = str(override.get("outputMode") or "static")
        if output_mode not in {"static", "video"}:
            raise ImageGenerationError("invalid_output_mode", f"Unsupported visual output mode: {output_mode}")
        hash_payload = {
            "projectId": project.id,
            "visualPlanId": plan.planId,
            "visualSourceHash": plan.sourceHash,
            "sceneId": scene.id,
            "blockId": scene.blockId,
            "subtitleIds": list(scene.subtitleIds),
            "start": start,
            "end": end,
            "finalPrompt": final_prompt,
            "negativePrompt": negative_prompt,
            "aspectRatio": aspect_ratio,
            "size": item_size,
            "providerId": item_provider,
            "routingMode": routing_mode,
            "routingReason": route.reason,
            "durationPolicy": duration_policy,
            "model": model,
        }
        items.append(
            {
                "sceneId": scene.id,
                "blockId": scene.blockId,
                "subtitleIds": list(scene.subtitleIds),
                "start": start,
                "end": end,
                "duration": end - start,
                "text": text,
                **values,
                "negativePrompt": negative_prompt,
                "finalPrompt": final_prompt,
                "aspectRatio": aspect_ratio,
                "size": item_size,
                "inputHash": _canonical_hash(hash_payload),
                "expectedFilename": f"scene_{index:03d}.mp4" if output_mode == "video" else f"scene_{index:03d}.png",
                "providerId": item_provider,
                "providerVersion": item_provider_version,
                "routingReason": route.reason,
                "routingConfidence": route.confidence,
                "durationPolicy": duration_policy,
                "requestedMediaType": scene.requestedMediaType,
                "outputMode": output_mode,
                "routeHints": dict((scene.metadata or {}).get("semantic") or {}),
                "status": "pending",
                "candidates": [],
            }
        )
    if not items:
        raise ImageGenerationError("scene_selection_empty", "Select at least one VisualPlan Scene")
    now = _now()
    batch = {
        "schemaVersion": 1,
        "batchId": batch_id,
        "projectId": project.id,
        "visualPlanId": plan.planId,
        "visualSourceHash": plan.sourceHash,
        "channel": channel,
        "providerId": provider_id,
        "model": model,
        "size": size,
        "candidateCount": candidate_count,
        "routingMode": routing_mode,
        "autoApprove": auto_approve,
        "status": "awaiting_agent" if channel == "agent" else "pending",
        "items": items,
        "createdAt": now,
        "updatedAt": now,
    }
    return _write_batch(batch)
