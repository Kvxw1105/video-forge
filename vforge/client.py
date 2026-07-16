"""Backend HTTP client. Single source of truth for API calls.
Used by both CLI and MCP server. No external deps — stdlib only.
"""
import json
import os
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


def create_project(name: str, ratio: str = "9:16", base: str = DEFAULT_BASE) -> dict:
    return _request("POST", "/api/projects", base=base,
                    json_body={"name": name, "canvas_ratio": ratio})


def update_project(pid: str, data: dict, base: str = DEFAULT_BASE) -> dict:
    return _request("PUT", f"/api/projects/{pid}", base=base, json_body=data)


def delete_project(pid: str, base: str = DEFAULT_BASE) -> dict:
    return _request("DELETE", f"/api/projects/{pid}", base=base)


# ── Assets ───────────────────────────────────────────────

def upload_asset(pid: str, file_path: str, base: str = DEFAULT_BASE) -> dict:
    return _request("POST", f"/api/projects/{pid}/assets", base=base,
                    files={"file": file_path})


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


def save_template(data: dict, base: str = DEFAULT_BASE) -> dict:
    return _request("POST", "/api/templates", base=base, json_body=data)


def delete_template(tid: str, base: str = DEFAULT_BASE) -> dict:
    return _request("DELETE", f"/api/templates/{tid}", base=base)


# ── Settings ─────────────────────────────────────────────

def get_tts_settings(base: str = DEFAULT_BASE) -> dict:
    return _request("GET", "/api/settings/tts", base=base)


def update_tts_settings(data: dict, base: str = DEFAULT_BASE) -> dict:
    return _request("PUT", "/api/settings/tts", base=base, json_body=data)
