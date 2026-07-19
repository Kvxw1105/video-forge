from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from config import JIANYING_DRAFT_DIR, PROJECTS_DIR
from frontend_host import resolve_frontend_dist, validate_frontend_dist
from models.system_readiness import ReadinessCheck, ReadinessResponse
from models.tts_settings import TtsSettings
from routers.library import LIBRARY_DIR
from routers.settings import get_tts_settings_raw


TEMP_DIR = Path(tempfile.gettempdir()) / "videoforge"
TTL_SECONDS = 10.0
_cache: tuple[float, ReadinessResponse] | None = None
_lock = Lock()


def _check(id: str, label: str, status: str, required: bool, message: str, details: dict[str, Any] | None = None) -> ReadinessCheck:
    return ReadinessCheck(id=id, label=label, status=status, required=required, message=message, details=details or {})


def aggregate_status(checks: list[ReadinessCheck]) -> str:
    if any(c.required and c.status == "fail" for c in checks):
        return "blocked"
    if any(c.status in {"warn", "fail"} for c in checks):
        return "degraded"
    return "ready"


def check_writable_directory(path: str | Path, id: str, label: str, required: bool) -> ReadinessCheck:
    target = Path(path)
    details = {"path": str(target.resolve())}
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / f".videoforge-readiness-{os.getpid()}-{time.time_ns()}"
        with probe.open("w", encoding="utf-8") as handle:
            handle.write("ok")
            handle.flush()
            os.fsync(handle.fileno())
        probe.unlink(missing_ok=True)
        return _check(id, label, "pass", required, f"{label}可写", details)
    except Exception as exc:
        return _check(id, label, "fail", required, f"{label}不可写", {**details, "error": type(exc).__name__})


def check_disk() -> ReadinessCheck:
    try:
        usage = shutil.disk_usage(str(PROJECTS_DIR))
        free_gb = usage.free / (1024 ** 3)
        status = "pass" if free_gb >= 5 else "warn" if free_gb >= 1 else "fail"
        message = "磁盘空间充足" if status == "pass" else "磁盘可用空间偏低" if status == "warn" else "磁盘可用空间不足"
        return _check("storage.disk", "磁盘空间", status, status == "fail", message, {
            "path": str(PROJECTS_DIR.resolve()), "freeBytes": usage.free,
            "freeGb": round(free_gb, 2), "totalBytes": usage.total,
        })
    except Exception as exc:
        return _check("storage.disk", "磁盘空间", "warn", False, "无法读取磁盘空间", {"error": type(exc).__name__})


def shutil_which(name: str) -> str | None:
    return shutil.which(name)


def check_ffmpeg() -> ReadinessCheck:
    path = shutil_which("ffmpeg")
    if not path:
        return _check("runtime.ffmpeg", "FFmpeg", "warn", False, "未找到FFmpeg", {})
    try:
        result = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=3, shell=False)
        first_line = (result.stdout or result.stderr or "").splitlines()[0][:200] if (result.stdout or result.stderr) else ""
        if result.returncode == 0:
            return _check("runtime.ffmpeg", "FFmpeg", "pass", False, "FFmpeg可用", {"path": path, "version": first_line})
        return _check("runtime.ffmpeg", "FFmpeg", "fail", False, "FFmpeg无法执行", {"path": path, "error": "non-zero exit"})
    except subprocess.TimeoutExpired:
        return _check("runtime.ffmpeg", "FFmpeg", "warn", False, "FFmpeg检测超时", {"path": path, "error": "timeout"})
    except Exception as exc:
        return _check("runtime.ffmpeg", "FFmpeg", "warn", False, "无法检测FFmpeg", {"path": path, "error": type(exc).__name__})


def check_jianying() -> ReadinessCheck:
    root = JIANYING_DRAFT_DIR
    if not root or not Path(root).is_dir():
        return _check("integration.jianying", "剪映草稿目录", "warn", False, "未检测到剪映草稿目录", {
            "detected": False, "draftDirectory": None, "directoryExists": False, "writable": False, "draftCount": 0,
        })
    path = Path(root)
    drafts = []
    try:
        drafts = [d for d in path.iterdir() if d.is_dir() and (d / "draft_content.json").is_file()]
        writable = os.access(path, os.W_OK)
        status = "pass" if writable else "fail"
        return _check("integration.jianying", "剪映草稿目录", status, False, "剪映草稿目录可写" if writable else "剪映草稿目录不可写", {
            "detected": True, "draftDirectory": str(path.resolve()), "directoryExists": True,
            "writable": writable, "draftCount": len(drafts),
        })
    except Exception as exc:
        return _check("integration.jianying", "剪映草稿目录", "warn", False, "无法读取剪映草稿目录", {"detected": True, "draftCount": len(drafts), "error": type(exc).__name__})


def check_tts() -> ReadinessCheck:
    try:
        settings = get_tts_settings_raw()
        engine = str(settings.engine or "edge").lower()
        missing: list[str] = []
        if engine == "edge":
            configured, available = True, True
        elif engine == "fish":
            configured = bool(settings.fishApiKey and settings.fishReferenceId)
            available = True
            if not settings.fishApiKey:
                missing.append("fishApiKey")
            if not settings.fishReferenceId:
                missing.append("fishReferenceId")
        elif engine == "manbo":
            configured = bool(settings.manboApiKey)
            available = False
            if not settings.manboApiKey:
                missing.append("manboApiKey")
        elif engine == "custom":
            configured = bool(settings.customApiUrl and settings.customApiKey)
            available = False
            if not settings.customApiUrl:
                missing.append("customApiUrl")
            if not settings.customApiKey:
                missing.append("customApiKey")
        else:
            configured, available = False, False
            missing.append("engine")
        status = "pass" if configured and available else "warn"
        return _check("integration.tts", "TTS配置", status, False, "TTS引擎可用" if status == "pass" else "TTS配置不完整", {
            "selectedEngine": engine, "configured": configured, "availableWithoutExternalKey": available,
            "missingFields": missing, **({"fallbackEngine": "edge"} if engine in {"manbo", "custom"} else {}),
        })
    except Exception as exc:
        return _check("integration.tts", "TTS配置", "warn", False, "无法读取TTS配置", {"error": type(exc).__name__})


def check_frontend(*, production_mode: bool) -> ReadinessCheck:
    try:
        dist = resolve_frontend_dist()
        validate_frontend_dist(dist)
        return _check("runtime.frontend", "前端生产构建", "pass", production_mode, "前端生产构建完整", {"path": str(dist)})
    except Exception as exc:
        return _check("runtime.frontend", "前端生产构建", "fail" if production_mode else "warn", production_mode, "前端生产构建缺失", {"path": str(resolve_frontend_dist()), "error": "build_missing"})


def check_runtime(production_mode: bool) -> ReadinessCheck:
    return _check("app.runtime", "应用运行状态", "pass", True, "VideoForge运行正常", {
        "name": "VideoForge", "version": "0.1.0", "productionMode": production_mode,
        "python": f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}",
        "os": os.name,
    })


def _safe_check(checker: Callable[[], ReadinessCheck], id: str, label: str, required: bool = False) -> ReadinessCheck:
    try:
        return checker()
    except Exception as exc:
        return _check(id, label, "fail" if required else "warn", required, f"{label}检测失败", {"error": type(exc).__name__})


def build_capabilities(checks: list[ReadinessCheck], jianying: ReadinessCheck | None = None, production_mode: bool = False) -> dict[str, bool]:
    by_id = {c.id: c for c in checks}
    jianying = jianying or by_id.get("integration.jianying")
    editing = all(by_id.get(key) and by_id[key].status == "pass" for key in ("storage.projects", "storage.library", "storage.temp"))
    ffmpeg_ok = by_id.get("runtime.ffmpeg") is not None and by_id["runtime.ffmpeg"].status == "pass"
    tts_ok = by_id.get("integration.tts") is not None and by_id["integration.tts"].status == "pass"
    direct_ok = bool(jianying and jianying.status == "pass")
    return {"projectEditing": editing, "voiceover": tts_ok, "previewRendering": editing and ffmpeg_ok,
            "jianyingZipExport": editing, "jianyingDirectExport": editing and direct_ok}


def run_checks(*, production_mode: bool = False) -> ReadinessResponse:
    checks = [
        _safe_check(lambda: check_runtime(production_mode), "app.runtime", "应用运行状态", True),
        _safe_check(lambda: check_writable_directory(PROJECTS_DIR, "storage.projects", "项目目录", True), "storage.projects", "项目目录", True),
        _safe_check(lambda: check_writable_directory(LIBRARY_DIR, "storage.library", "素材库目录", True), "storage.library", "素材库目录", True),
        _safe_check(lambda: check_writable_directory(TEMP_DIR, "storage.temp", "临时目录", True), "storage.temp", "临时目录", True),
        _safe_check(check_disk, "storage.disk", "磁盘空间"),
        _safe_check(check_ffmpeg, "runtime.ffmpeg", "FFmpeg"),
        _safe_check(check_jianying, "integration.jianying", "剪映草稿目录"),
        _safe_check(check_tts, "integration.tts", "TTS配置"),
        _safe_check(lambda: check_frontend(production_mode=production_mode), "runtime.frontend", "前端生产构建", production_mode),
    ]
    status = aggregate_status(checks)
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for item in checks:
        counts[item.status] += 1
    return ReadinessResponse(status=status, checkedAt=datetime.now(timezone.utc),
        app={"name": "VideoForge", "version": "0.1.0", "productionMode": production_mode},
        checks=checks, capabilities=build_capabilities(checks),
        summary={"passed": counts["pass"], "warnings": counts["warn"], "failed": counts["fail"]})


def clear_cache() -> None:
    global _cache
    with _lock:
        _cache = None


def get_readiness(*, refresh: bool = False, production_mode: bool = False) -> ReadinessResponse:
    global _cache
    now = time.monotonic()
    with _lock:
        if not refresh and _cache and now - _cache[0] < TTL_SECONDS and _cache[1].app.productionMode == production_mode:
            return _cache[1]
        result = run_checks(production_mode=production_mode)
        _cache = (now, result)
        return result
