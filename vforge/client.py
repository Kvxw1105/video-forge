"""Backend HTTP client. Single source of truth for API calls.
Used by both CLI and MCP server. No external deps — stdlib only.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

DEFAULT_BASE = os.environ.get("VFORGE_BASE", "http://localhost:8000")


class VForgeError(RuntimeError):
    """Raised when backend returns non-2xx. Carries the parsed error body."""
    def __init__(self, status: int, body: str):
        self.status = status
        try:
            self.detail = json.loads(body).get("detail", body)
        except Exception:
            self.detail = body
        super().__init__(f"HTTP {status}: {self.detail}")


def _request(method: str, path: str, *, base: str = DEFAULT_BASE,
             json_body: Any = None, files: Optional[dict] = None,
             timeout: float = 300.0) -> Any:
    url = base.rstrip("/") + path
    headers = {}
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if files is not None:
        # multipart/form-data (minimal: single file per request, like upload_asset)
        boundary = "----vforgeboundary"
        body = bytearray()
        for key, val in files.items():
            body += f"--{boundary}\r\n".encode()
            if isinstance(val, tuple):
                # (filename, bytes)
                fname, content = val
                body += (
                    f'Content-Disposition: form-data; name="{key}"; '
                    f'filename="{fname}"\r\n'
                    f"Content-Type: application/octet-stream\r\n\r\n"
                ).encode()
                body += content
            else:
                # file path
                fpath = Path(val)
                body += (
                    f'Content-Disposition: form-data; name="{key}"; '
                    f'filename="{fpath.name}"\r\n'
                    f"Content-Type: application/octet-stream\r\n\r\n"
                ).encode()
                body += fpath.read_bytes()
            body += b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        data = bytes(body)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body_bytes = resp.read()
            ct = resp.headers.get("Content-Type", "")
            if "application/json" in ct:
                return json.loads(body_bytes) if body_bytes else None
            return body_bytes
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise VForgeError(e.code, body) from None
    except urllib.error.URLError as e:
        raise VForgeError(0, str(e.reason)) from None


# ── Project ──────────────────────────────────────────────

def health(base: str = DEFAULT_BASE) -> dict:
    return _request("GET", "/api/health", base=base)


def list_projects(base: str = DEFAULT_BASE) -> list:
    return _request("GET", "/api/projects", base=base)


def get_project(pid: str, base: str = DEFAULT_BASE) -> dict:
    return _request("GET", f"/api/projects/{pid}", base=base)


def create_project(name: str, ratio: str = "9:16", base: str = DEFAULT_BASE, template_id: str | None = None) -> dict:
    payload = {"name": name, "canvas_ratio": ratio}
    if template_id is not None:
        payload["template_id"] = template_id
    return _request("POST", "/api/projects", base=base,
                    json_body=payload)


def update_project(pid: str, data: dict, base: str = DEFAULT_BASE) -> dict:
    return _request("PUT", f"/api/projects/{pid}", base=base, json_body=data)


def delete_project(pid: str, base: str = DEFAULT_BASE) -> dict:
    return _request("DELETE", f"/api/projects/{pid}", base=base)


# ── Assets ───────────────────────────────────────────────

def upload_asset(pid: str, file_path: str, base: str = DEFAULT_BASE) -> dict:
    return _request("POST", f"/api/projects/{pid}/assets", base=base,
                    files={"file": file_path})


def render_stickman_assets(
    pid: str,
    *,
    source_mode: str = "visual_plan",
    scene_ids: list[str] | None = None,
    export_png: bool = True,
    bind_to_project: bool = True,
    replace_manual_edits: bool = False,
    force_replace_user_asset: bool = False,
    base: str = DEFAULT_BASE,
) -> dict:
    return _request("POST", f"/api/projects/{pid}/visual-assets/stickman/render", base=base, json_body={
        "sourceMode": source_mode,
        "sceneIds": scene_ids or [],
        "exportSvg": True,
        "exportPng": export_png,
        "generateContactSheet": True,
        "bindToProject": bind_to_project,
        "replaceManualEdits": replace_manual_edits,
        "forceReplaceUserAsset": force_replace_user_asset,
        "routing": {"allowLlm": False, "minimumConfidence": 0.65, "lowConfidencePolicy": "fallback"},
    })


def regenerate_stickman_scene(
    pid: str,
    scene_id: str,
    *,
    export_png: bool = True,
    replace_manual_edits: bool = False,
    base: str = DEFAULT_BASE,
) -> dict:
    return _request("POST", f"/api/projects/{pid}/visual-assets/stickman/scenes/{scene_id}/regenerate", base=base, json_body={
        "sourceMode": "visual_plan",
        "exportSvg": True,
        "exportPng": export_png,
        "generateContactSheet": True,
        "bindToProject": True,
        "replaceManualEdits": replace_manual_edits,
        "routing": {"allowLlm": False, "minimumConfidence": 0.65, "lowConfidencePolicy": "fallback"},
    })


def get_stickman_generation_run(pid: str, run_id: str, base: str = DEFAULT_BASE) -> dict:
    return _request("GET", f"/api/projects/{pid}/visual-assets/stickman/runs/{run_id}", base=base)


# ── Voiceover ────────────────────────────────────────────

def generate_voiceover(pid: str, text: str, *, engine: str = "edge",
                       speed: int = 0, base: str = DEFAULT_BASE) -> dict:
    return _request("POST", f"/api/projects/{pid}/voiceover", base=base,
                    json_body={"text": text, "engine": engine, "speed": speed})


# ── Subtitles ────────────────────────────────────────────

def import_srt(pid: str, file_path: str, base: str = DEFAULT_BASE) -> dict:
    return _request("POST", f"/api/projects/{pid}/subtitles/import-srt",
                    base=base, files={"file": file_path})


# ── Render & Export ──────────────────────────────────────

def render_preview(pid: str, base: str = DEFAULT_BASE) -> dict:
    return _request("POST", f"/api/projects/{pid}/preview", base=base)


def export_jianying_zip(pid: str, output_path: str, base: str = DEFAULT_BASE) -> str:
    """Download the jianying ZIP and save to output_path. Returns the saved path."""
    data = _request("POST", f"/api/projects/{pid}/export/jianying", base=base)
    Path(output_path).write_bytes(data)
    return output_path


def export_jianying_direct(pid: str, base: str = DEFAULT_BASE) -> dict:
    return _request("POST", f"/api/projects/{pid}/export/jianying-direct", base=base)


def jianying_status(base: str = DEFAULT_BASE) -> dict:
    return _request("GET", "/api/jianying-status", base=base)


# ── Templates ────────────────────────────────────────────

def list_templates(base: str = DEFAULT_BASE) -> list:
    return _request("GET", "/api/templates", base=base)


def get_template(template_id: str, base: str = DEFAULT_BASE) -> dict:
    return _request("GET", f"/api/templates/{template_id}", base=base)


def save_template(data: dict, base: str = DEFAULT_BASE) -> dict:
    return _request("POST", "/api/templates", base=base, json_body=data)


def delete_template(tid: str, base: str = DEFAULT_BASE) -> dict:
    return _request("DELETE", f"/api/templates/{tid}", base=base)


# Template batch production. The backend owns planning, persistence, and execution.
def plan_template_batch(spec: dict, base: str = DEFAULT_BASE) -> dict:
    return _request("POST", "/api/batches/template-production/plan", base=base, json_body=spec)


def start_template_batch(spec: dict, base: str = DEFAULT_BASE) -> dict:
    return _request("POST", "/api/batches/template-production", base=base, json_body=spec)


def list_template_batches(base: str = DEFAULT_BASE) -> list:
    return _request("GET", "/api/batches/template-production", base=base)


def get_template_batch(batch_id: str, base: str = DEFAULT_BASE) -> dict:
    return _request("GET", f"/api/batches/template-production/{batch_id}", base=base)


def resume_template_batch(batch_id: str, base: str = DEFAULT_BASE) -> dict:
    return _request("POST", f"/api/batches/template-production/{batch_id}/resume", base=base, json_body={})


def get_template_batch_manifest(batch_id: str, base: str = DEFAULT_BASE) -> dict:
    return _request("GET", f"/api/batches/template-production/{batch_id}/manifest", base=base)


def wait_template_batch(batch_id: str, timeout_seconds: float = 3600, poll_interval: float = 1, base: str = DEFAULT_BASE) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while True:
        result = get_template_batch(batch_id, base=base)
        if result.get("status") in {"succeeded", "partial", "failed"}:
            return result
        if time.monotonic() >= deadline:
            raise VForgeError(408, "template batch wait timed out")
        time.sleep(max(0.1, poll_interval))


def get_visual_planning_context(pid: str, base: str = DEFAULT_BASE) -> dict: return _request("GET", f"/api/projects/{pid}/visual-plan/context", base=base)
def propose_visual_scene_plan(pid: str, data: dict, base: str = DEFAULT_BASE) -> dict: return _request("POST", f"/api/projects/{pid}/visual-plan/propose", base=base, json_body=data)
def get_visual_scene_plan(pid: str, base: str = DEFAULT_BASE) -> dict: return _request("GET", f"/api/projects/{pid}/visual-plan", base=base)
def set_visual_scene_plan(pid: str, plan: dict, expected_updated_at: str | None = None, base: str = DEFAULT_BASE) -> dict:
    payload={"plan":plan};
    if expected_updated_at is not None: payload["expectedUpdatedAt"]=expected_updated_at
    return _request("PUT", f"/api/projects/{pid}/visual-plan", base=base,json_body=payload)
def validate_visual_scene_plan(pid: str, base: str = DEFAULT_BASE) -> dict: return _request("POST", f"/api/projects/{pid}/visual-plan/validate", base=base,json_body={})
def export_visual_generation_pack(pid: str, base: str = DEFAULT_BASE) -> dict: return _request("POST", f"/api/projects/{pid}/visual-plan/generation-pack", base=base,json_body={})
def import_visual_scene_folder(pid: str, folder: str, base: str = DEFAULT_BASE) -> dict: return _request("POST", f"/api/projects/{pid}/visual-plan/import-folder", base=base,json_body={"folder":folder})
def compile_visual_scene_variant(pid: str, variant_id: str, base: str = DEFAULT_BASE) -> dict: return _request("POST", f"/api/projects/{pid}/visual-plan/compile/{variant_id}", base=base,json_body={})

def factory_pending_visuals(batch_id: str, base: str = DEFAULT_BASE) -> dict: return _request("GET", f"/api/agent-factory/batches/{batch_id}/pending-visuals", base=base)
def factory_import_visuals(batch_id: str, item_id: str, data: dict, base: str = DEFAULT_BASE) -> dict: return _request("POST", f"/api/agent-factory/batches/{batch_id}/items/{item_id}/visuals/import",base=base,json_body=data)
def factory_validate_visuals(batch_id: str, item_id: str, base: str = DEFAULT_BASE) -> dict: return _request("POST", f"/api/agent-factory/batches/{batch_id}/items/{item_id}/visuals/validate",base=base,json_body={})
def factory_resume_item(batch_id: str, item_id: str, base: str = DEFAULT_BASE) -> dict: return _request("POST", f"/api/agent-factory/batches/{batch_id}/items/{item_id}/resume",base=base,json_body={})
def factory_resume_batch(batch_id: str, base: str = DEFAULT_BASE) -> dict: return _request("POST", f"/api/agent-factory/batches/{batch_id}/resume",base=base,json_body={})
def factory_continue(batch_id: str, base: str = DEFAULT_BASE) -> dict: return _request("POST", f"/api/agent-factory/batches/{batch_id}/continue",base=base,json_body={})
def factory_plan(spec: dict, base: str = DEFAULT_BASE) -> dict: return plan_template_batch(spec,base)
def factory_start(spec: dict, base: str = DEFAULT_BASE) -> dict: return start_template_batch(spec,base)
def factory_status(batch_id: str, base: str = DEFAULT_BASE) -> dict: return get_template_batch(batch_id,base)
def factory_manifest(batch_id: str, base: str = DEFAULT_BASE) -> dict: return get_template_batch_manifest(batch_id,base)


# ── Settings ─────────────────────────────────────────────

def get_tts_settings(base: str = DEFAULT_BASE) -> dict:
    return _request("GET", "/api/settings/tts", base=base)


def update_tts_settings(data: dict, base: str = DEFAULT_BASE) -> dict:
    return _request("PUT", "/api/settings/tts", base=base, json_body=data)


# Structured Content / Composition semantic operations
def list_structured_projects(base: str = DEFAULT_BASE) -> list:
    return _request("GET", "/api/projects/structured/catalog", base=base)


def get_structured_project_status(pid: str, base: str = DEFAULT_BASE) -> dict:
    project = get_project(pid, base=base)
    structured = project.get("structuredContent") or {}
    episode = structured.get("episode") or {}
    try:
        audio_status = _request("GET", f"/api/projects/{pid}/structured/audio/status", base=base)
    except VForgeError:
        audio_status = {"hasAlignment": False, "warnings": []}
    return {"projectId": pid, "structured": bool(project.get("structuredContent")), "composition": project.get("composition"), "episode": episode, "audio": audio_status, "updatedAt": project.get("updated_at")}


def list_structured_variants(pid: str, base: str = DEFAULT_BASE) -> list:
    project = get_project(pid, base=base)
    episode = ((project.get("structuredContent") or {}).get("episode") or {})
    return [{"id": item.get("id"), "name": item.get("name", ""), "blockCount": len(item.get("blockIds") or [])} for item in episode.get("variants") or []]


def compile_structured_variant_summary(pid: str, variant_id: str, base: str = DEFAULT_BASE) -> dict:
    return _request("GET", f"/api/projects/{pid}/structured/variants/{variant_id}/compile", base=base)


def parse_structured_markdown(text: str, base: str = DEFAULT_BASE) -> dict:
    return _request("POST", "/api/structured/import/parse", base=base, json_body={"text": text, "format": "auto"})


def create_structured_project(name: str, episode: dict, ratio: str = "9:16", base: str = DEFAULT_BASE) -> dict:
    return _request("POST", "/api/projects/structured", base=base, json_body={"name": name, "episode": episode, "canvas": {"ratio": ratio}})


def get_structured_episode_draft(pid: str, base: str = DEFAULT_BASE) -> dict:
    return _request("GET", f"/api/projects/{pid}/structured/draft", base=base)


def update_structured_episode_draft(pid: str, data: dict, expected_updated_at: str | None = None, base: str = DEFAULT_BASE) -> dict:
    payload = dict(data)
    if expected_updated_at is not None:
        payload["expectedUpdatedAt"] = expected_updated_at
    return _request("PATCH", f"/api/projects/{pid}/structured/draft", base=base, json_body=payload)


def _guarded_update(pid: str, data: dict, expected_updated_at: str | None, base: str = DEFAULT_BASE):
    current = get_project(pid, base=base)
    actual = current.get("updated_at")
    if expected_updated_at is not None and actual != expected_updated_at:
        return {"status": "conflict", "expectedUpdatedAt": expected_updated_at, "actualUpdatedAt": actual}
    return update_project(pid, data, base=base)


def create_composition_project(name: str, ratio: str = "9:16", base: str = DEFAULT_BASE) -> dict:
    project = create_project(name, ratio, base=base)
    composition = {"schemaVersion": 1, "compositionId": f"composition_{project['id']}", "title": name, "items": [], "metadata": {}}
    return update_project(project["id"], {"templateId": "structured_composition", "composition": composition}, base=base)


def get_composition(pid: str, base: str = DEFAULT_BASE) -> dict:
    project = get_project(pid, base=base)
    if not project.get("composition"):
        raise VForgeError(409, "Project does not contain composition")
    return {"projectId": pid, "updatedAt": project.get("updated_at"), "composition": project["composition"]}


def set_composition_items(pid: str, items: list[dict], expected_updated_at: str | None = None, base: str = DEFAULT_BASE):
    current = get_project(pid, base=base)
    composition = current.get("composition")
    if not composition:
        raise VForgeError(409, "Project does not contain composition")
    if not isinstance(items, list):
        raise VForgeError(422, "items must be a list")
    updated = dict(composition); updated["items"] = items
    return _guarded_update(pid, {"composition": updated}, expected_updated_at, base=base)


def move_composition_item(pid: str, item_id: str, direction: str, expected_updated_at: str | None = None, base: str = DEFAULT_BASE):
    current = get_project(pid, base=base); composition = current.get("composition")
    if not composition: raise VForgeError(409, "Project does not contain composition")
    items = list(composition.get("items") or []); index = next((i for i, item in enumerate(items) if item.get("id") == item_id), None)
    if index is None: raise VForgeError(404, f"Composition item not found: {item_id}")
    target = index - 1 if direction == "up" else index + 1 if direction == "down" else -1
    if target < 0 or target >= len(items): return {"status": "ok", "unchanged": True, "updatedAt": current.get("updated_at")}
    items[index], items[target] = items[target], items[index]
    updated = dict(composition); updated["items"] = items
    return _guarded_update(pid, {"composition": updated}, expected_updated_at, base=base)


def set_composition_item_enabled(pid: str, item_id: str, enabled: bool, expected_updated_at: str | None = None, base: str = DEFAULT_BASE):
    current = get_project(pid, base=base); composition = current.get("composition")
    if not composition: raise VForgeError(409, "Project does not contain composition")
    items = list(composition.get("items") or []); found = False
    for item in items:
        if item.get("id") == item_id: item["enabled"] = bool(enabled); found = True
    if not found: raise VForgeError(404, f"Composition item not found: {item_id}")
    updated = dict(composition); updated["items"] = items
    return _guarded_update(pid, {"composition": updated}, expected_updated_at, base=base)


def set_structured_block_enabled(pid: str, block_id: str, enabled: bool, expected_updated_at: str | None = None, base: str = DEFAULT_BASE):
    current = get_project(pid, base=base); structured = current.get("structuredContent") or {}; episode = structured.get("episode") or {}
    blocks = list(episode.get("blocks") or []); found = False
    for block in blocks:
        if block.get("id") == block_id: block["enabled"] = bool(enabled); found = True
    if not found: raise VForgeError(404, f"Block not found: {block_id}")
    updated_structured = dict(structured); updated_structured["episode"] = {**episode, "blocks": blocks}
    return _guarded_update(pid, {"structuredContent": updated_structured}, expected_updated_at, base=base)


def set_variant_block_order(pid: str, variant_id: str, block_ids: list[str], expected_updated_at: str | None = None, base: str = DEFAULT_BASE):
    current = get_project(pid, base=base); structured = current.get("structuredContent") or {}; episode = structured.get("episode") or {}
    known = {block.get("id") for block in episode.get("blocks") or []}
    if len(block_ids) != len(set(block_ids)) or not set(block_ids).issubset(known):
        raise VForgeError(422, "blockIds must contain existing blocks without duplicates")
    variants = list(episode.get("variants") or []); found = False
    for variant in variants:
        if variant.get("id") == variant_id: variant["blockIds"] = list(block_ids); found = True
    if not found: raise VForgeError(404, f"Variant not found: {variant_id}")
    updated_structured = dict(structured); updated_structured["episode"] = {**episode, "variants": variants}
    return _guarded_update(pid, {"structuredContent": updated_structured}, expected_updated_at, base=base)


def compile_composition(pid: str, base: str = DEFAULT_BASE) -> dict:
    return _request("POST", f"/api/projects/{pid}/composition/compile", base=base)


def preview_composition(pid: str, base: str = DEFAULT_BASE) -> dict:
    return _request("POST", f"/api/projects/{pid}/composition/preview", base=base)


def export_composition_to_jianying(pid: str, base: str = DEFAULT_BASE) -> dict:
    return _request("POST", f"/api/projects/{pid}/composition/export/jianying-direct", base=base, json_body={"policy": "create_new"})
