from __future__ import annotations

import base64
import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from agent_runtime.ai_image_settings import AIImageProviderSettings, load_ai_image_provider
from services.project_service import _project_dir, get_project, update_project


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Base URL must be a complete http(s) URL")
    return value.strip().rstrip("/")


def _headers(settings: AIImageProviderSettings) -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.apiKey}"} if settings.apiKey else {}


def fetch_models(settings: AIImageProviderSettings) -> dict[str, Any]:
    import time
    url = f"{_base_url(settings.baseUrl)}/models"
    started = time.monotonic()
    try:
        response = httpx.get(url, headers=_headers(settings), timeout=settings.timeoutSeconds)
        latency = round((time.monotonic() - started) * 1000)
        if response.status_code >= 400:
            return {"ok": False, "latencyMs": latency, "models": [], "message": response.text[:240] or f"HTTP {response.status_code}"}
        raw = response.json()
        rows = raw.get("data", raw.get("models", raw if isinstance(raw, list) else []))
        models = [{"id": str(row.get("id") or row.get("name")), "name": str(row.get("name") or row.get("id"))} for row in rows if isinstance(row, dict) and (row.get("id") or row.get("name"))]
        return {"ok": True, "latencyMs": latency, "models": models, "message": f"Connected: {len(models)} models"}
    except (httpx.HTTPError, ValueError) as exc:
        return {"ok": False, "latencyMs": None, "models": [], "message": str(exc)}


def _batch_path(project_id: str, batch_id: str) -> Path:
    return _project_dir(project_id) / "visual-assets" / "ai-image" / batch_id / "manifest.json"


def _write_batch(project_id: str, batch: dict[str, Any]) -> None:
    path = _batch_path(project_id, batch["batchId"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def get_batch(project_id: str, batch_id: str) -> dict[str, Any]:
    path = _batch_path(project_id, batch_id)
    if not path.is_file():
        raise FileNotFoundError(batch_id)
    return json.loads(path.read_text(encoding="utf-8"))


def create_batch(project_id: str, items: list[dict[str, Any]], *, model: str, size: str, candidate_count: int) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise KeyError("project_not_found")
    scene_ids = {scene.id for scene in (((project.structuredContent.episode.visualPlan.scenes if project.structuredContent and project.structuredContent.episode.visualPlan else [])))}
    normalized = []
    for index, item in enumerate(items, 1):
        scene_id = str(item.get("sceneId") or "").strip()
        prompt = str(item.get("prompt") or "").strip()
        if scene_id not in scene_ids or not prompt:
            raise ValueError(f"invalid generation item at index {index}")
        normalized.append({"sceneId": scene_id, "prompt": prompt, "negativePrompt": str(item.get("negativePrompt") or ""), "status": "queued", "candidates": [], "error": None})
    if not normalized:
        raise ValueError("at least one scene prompt is required")
    batch = {"batchId": f"aiimg_{uuid4().hex[:12]}", "projectId": project_id, "status": "queued", "createdAt": _now(), "updatedAt": _now(), "model": model, "size": size, "candidateCount": candidate_count, "items": normalized}
    _write_batch(project_id, batch)
    return batch


def run_batch(project_id: str, batch_id: str, update) -> dict[str, Any]:
    settings = load_ai_image_provider()
    if not settings.enabled or not settings.baseUrl or not settings.model:
        raise RuntimeError("AI image provider is not configured")
    batch = get_batch(project_id, batch_id)
    batch["status"] = "running"; batch["updatedAt"] = _now(); _write_batch(project_id, batch)
    total = len(batch["items"])
    completed = 0
    with ThreadPoolExecutor(max_workers=min(settings.maxConcurrency, total), thread_name_prefix="ai-image") as executor:
        futures = {executor.submit(_generate_item, project_id, batch_id, index, item, settings, batch["model"], batch["size"], batch["candidateCount"]): index for index, item in enumerate(batch["items"])}
        for future in as_completed(futures):
            index = futures[future]
            try:
                batch["items"][index] = future.result()
            except Exception as exc:
                batch["items"][index] = {**batch["items"][index], "status": "failed", "error": str(exc)}
            completed += 1
            batch["updatedAt"] = _now(); _write_batch(project_id, batch)
            update(5 + 90 * completed / total, "generating", f"Generated {completed}/{total} scenes")
    batch["status"] = "succeeded" if all(item["status"] == "succeeded" for item in batch["items"]) else "partial"
    batch["updatedAt"] = _now(); _write_batch(project_id, batch)
    return batch


def _generate_item(project_id: str, batch_id: str, index: int, item: dict[str, Any], settings: AIImageProviderSettings, model: str, size: str, candidate_count: int) -> dict[str, Any]:
    payload = {"model": model or settings.model, "prompt": item["prompt"], "n": candidate_count, "size": size, "response_format": "b64_json"}
    if item.get("negativePrompt"):
        payload["negative_prompt"] = item["negativePrompt"]
    response = httpx.post(f"{_base_url(settings.baseUrl)}/images/generations", headers={**_headers(settings), "Content-Type": "application/json"}, json=payload, timeout=settings.timeoutSeconds)
    response.raise_for_status()
    rows = response.json().get("data") or []
    if not rows:
        raise RuntimeError("upstream returned no images")
    output_dir = _batch_path(project_id, batch_id).parent / item["sceneId"]
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates = []
    for candidate_index, row in enumerate(rows, 1):
        destination = output_dir / f"candidate_{candidate_index:02d}.png"
        if row.get("b64_json"):
            destination.write_bytes(base64.b64decode(row["b64_json"]))
        elif row.get("url"):
            download = httpx.get(str(row["url"]), timeout=settings.timeoutSeconds)
            download.raise_for_status(); destination.write_bytes(download.content)
        else:
            continue
        candidates.append({"id": f"{item['sceneId']}_{candidate_index}", "path": str(destination.relative_to(_project_dir(project_id))).replace("\\", "/"), "status": "pending", "revisedPrompt": row.get("revised_prompt")})
    if not candidates:
        raise RuntimeError("upstream returned images without b64_json or url")
    return {**item, "status": "succeeded", "candidates": candidates, "error": None}


def approve_candidates(project_id: str, batch_id: str, selections: list[dict[str, str]]) -> dict[str, Any]:
    batch = get_batch(project_id, batch_id)
    project = get_project(project_id)
    if project is None:
        raise KeyError("project_not_found")
    selected = {str(row.get("sceneId")): str(row.get("candidateId")) for row in selections}
    assets = [asset.model_dump() if hasattr(asset, "model_dump") else dict(asset) for asset in project.assets]
    scenes = {scene.id: scene.model_dump() for scene in project.structuredContent.episode.visualPlan.scenes}
    root = _project_dir(project_id); asset_dir = root / "assets"; asset_dir.mkdir(exist_ok=True)
    bound = []
    for item in batch["items"]:
        candidate = next((row for row in item.get("candidates", []) if row["id"] == selected.get(item["sceneId"])), None)
        if not candidate:
            continue
        source = root / candidate["path"]
        destination = asset_dir / f"ai_{item['sceneId']}_{Path(candidate['path']).name}"
        shutil.copy2(source, destination)
        asset_id = f"visual_ai_image_{item['sceneId']}"
        assets = [asset for asset in assets if asset.get("id") != asset_id]
        assets.append({"id": asset_id, "type": "image", "name": destination.name, "path": f"assets/{destination.name}", "metadata": {"generatedBy": "ai_image", "batchId": batch_id, "sceneId": item["sceneId"], "prompt": item["prompt"], "model": batch["model"]}})
        scenes[item["sceneId"]]["visualAssetIds"] = [asset_id]
        scenes[item["sceneId"]]["primaryAssetId"] = asset_id
        candidate["status"] = "approved"; bound.append({"sceneId": item["sceneId"], "assetId": asset_id})
    plan = project.structuredContent.episode.visualPlan.model_dump()
    plan["scenes"] = [scenes[scene.id] for scene in project.structuredContent.episode.visualPlan.scenes]
    updated = update_project(project_id, {"assets": assets, "structuredContent": {**project.structuredContent.model_dump(), "episode": {**project.structuredContent.episode.model_dump(), "visualPlan": plan}}})
    batch["updatedAt"] = _now(); _write_batch(project_id, batch)
    return {"bound": bound, "updatedAt": updated.updated_at, "batch": batch}
