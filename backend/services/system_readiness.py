from __future__ import annotations

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
from services.jianying_status import inspect_jianying_status


TEMP_DIR = Path(tempfile.gettempdir()) / "videoforge"
TTL_SECONDS = 10.0
_cache: tuple[float, tuple[bool, str | None, str, str], ReadinessResponse] | None = None
_lock = Lock()


def _check(id: str, label: str, status: str, required: bool, message: str, details: dict[str, Any] | None = None) -> ReadinessCheck:
    return ReadinessCheck(id=id, label=label, status=status, required=required, message=message, details=details or {})


def aggregate_status(checks: list[ReadinessCheck]) -> str:
    if any(c.required and c.status == "fail" for c in checks):
        return "blocked"
    if any(c.status in {"warn", "fail"} for c in checks):
        return "degraded"
    return "ready"


def _legacy_check_writable_directory(path: str | Path, id: str, label: str, required: bool) -> ReadinessCheck:
    target = Path(path)
    details = {"path": str(target.resolve())}
    probe = None
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / f".videoforge-readiness-{os.getpid()}-{time.time_ns()}.tmp"
        with probe.open("w", encoding="utf-8") as handle:
            handle.write("ok")
            handle.flush()
            os.fsync(handle.fileno())
        return _check(id, label, "pass", required, f"{label}可写", details)
    except Exception as exc:
        return _check(id, label, "fail", required, f"{label}不可写", {**details, "error": type(exc).__name__})
    finally:
        if probe is not None:
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass


def check_writable_directory_v2(path: str | Path, id: str, label: str, required: bool) -> ReadinessCheck:
    target = Path(path)
    details = {"path": str(target.resolve())}
    probe = None
    write_error = None
    cleanup_error = None
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / f".videoforge-readiness-{os.getpid()}-{time.time_ns()}.tmp"
        with probe.open("w", encoding="utf-8") as handle:
            handle.write("ok")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception as exc:
        write_error = exc
    finally:
        if probe is not None:
            for attempt in range(2):
                try:
                    probe.unlink(missing_ok=True)
                    break
                except OSError as exc:
                    if attempt == 1:
                        cleanup_error = exc
                    else:
                        time.sleep(0.05)
    if cleanup_error is not None:
        return _check(id, label, "fail", required, f"{label} cleanup failed", {**details, "error": "cleanup_failed", "errorType": type(cleanup_error).__name__})
    if write_error is not None:
        return _check(id, label, "fail", required, f"{label} is not writable", {**details, "error": type(write_error).__name__})
    return _check(id, label, "pass", required, f"{label} writable", details)


check_writable_directory = check_writable_directory_v2


def check_disk_v2() -> ReadinessCheck:
    try:
        usage = shutil.disk_usage(str(PROJECTS_DIR))
        free_gb = usage.free / (1024 ** 3)
        status = "pass" if free_gb >= 5 else "warn" if free_gb >= 1 else "fail"
        return _check("storage.disk", "storage.disk", status, True, "Disk space available" if status == "pass" else "Disk space is low" if status == "warn" else "Disk space is insufficient", {
            "path": str(PROJECTS_DIR.resolve()), "freeBytes": usage.free, "freeGb": round(free_gb, 2), "totalBytes": usage.total,
        })
    except Exception as exc:
        return _check("storage.disk", "storage.disk", "warn", True, "Unable to inspect disk space", {"error": type(exc).__name__})


check_disk = check_disk_v2


def _legacy_check_disk() -> ReadinessCheck:
    try:
        usage = shutil.disk_usage(str(PROJECTS_DIR))
        free_gb = usage.free / (1024 ** 3)
        status = "pass" if free_gb >= 5 else "warn" if free_gb >= 1 else "fail"
        message = "磁盘空间充足" if status == "pass" else "磁盘可用空间偏低" if status == "warn" else "磁盘可用空间不足"
        return _check("storage.disk", "磁盘空间", status, True, message, {
            "path": str(PROJECTS_DIR.resolve()), "freeBytes": usage.free,
            "freeGb": round(free_gb, 2), "totalBytes": usage.total,
        })
    except Exception as exc:
        return _check("storage.disk", "磁盘空间", "warn", False, "无法读取磁盘空间", {"error": type(exc).__name__})


check_disk = check_disk_v2


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


def _legacy_check_jianying() -> ReadinessCheck:
    status = inspect_jianying_status(JIANYING_DRAFT_DIR)
    if not status["directoryExists"]:
        return _check("integration.jianying", "剪映草稿目录", "warn", False, "未检测到剪映草稿目录", {
            "detected": False, "draftDirectory": None, "directoryExists": False, "writable": False, "draftCount": 0,
        })
    write_check = check_writable_directory(JIANYING_DRAFT_DIR, "integration.jianying", "剪映草稿目录", False)
    state = "pass" if write_check.status == "pass" else "fail"
    return _check("integration.jianying", "剪映草稿目录", state, False, "剪映草稿目录可写" if state == "pass" else "剪映草稿目录不可写", {
        "detected": True, "draftDirectory": status["path"], "directoryExists": True,
        "writable": status["writable"], "draftCount": status["draftCount"],
    })


def check_jianying_v2() -> ReadinessCheck:
    status = inspect_jianying_status(JIANYING_DRAFT_DIR)
    if not status["directoryExists"]:
        return _check("integration.jianying", "JianYing draft directory", "warn", False, "JianYing draft directory was not detected", {
            "detected": False, "draftDirectory": None, "directoryExists": False, "writable": False, "draftCount": 0,
        })
    write_check = check_writable_directory(JIANYING_DRAFT_DIR, "integration.jianying", "JianYing draft directory", False)
    writable = write_check.status == "pass"
    details = {"detected": True, "draftDirectory": status["path"], "directoryExists": True, "writable": writable, "draftCount": status["draftCount"]}
    if "error" in write_check.details:
        details["error"] = write_check.details["error"]
    if "errorType" in write_check.details:
        details["errorType"] = write_check.details["errorType"]
    return _check("integration.jianying", "JianYing draft directory", "pass" if writable else "fail", False, "JianYing draft directory writable" if writable else "JianYing draft directory is not writable", details)


check_jianying = check_jianying_v2


def _legacy_check_tts() -> ReadinessCheck:
    try:
        settings = get_tts_settings_raw()
        engine = str(settings.engine or "edge").lower()
        missing: list[str] = []
        if engine == "edge":
            configured, available, voiceover_available = True, True, True
        elif engine == "fish_audio":
            configured = bool(settings.fishApiKey and settings.fishReferenceId)
            available, voiceover_available = False, configured
            if not settings.fishApiKey:
                missing.append("fishApiKey")
            if not settings.fishReferenceId:
                missing.append("fishReferenceId")
        elif engine == "manbo":
            configured = bool(settings.manboApiKey and settings.manboApiUrl)
            available, voiceover_available = False, configured
            if not settings.manboApiKey:
                missing.append("manboApiKey")
        elif engine == "custom":
            configured = bool(settings.customApiUrl)
            available, voiceover_available = True, configured
            if not settings.customApiUrl:
                missing.append("customApiUrl")
        elif engine == "none":
            configured, available, voiceover_available = True, True, False
        else:
            configured, available, voiceover_available = False, False, False
            missing.append("engine")
        status = "pass" if configured else "warn"
        return _check("integration.tts", "TTS配置", status, False, "TTS引擎可用" if status == "pass" else "TTS配置不完整", {
            "selectedEngine": engine, "configured": configured, "availableWithoutExternalKey": available,
            "voiceoverAvailable": voiceover_available, "missingFields": missing,
            **({"authConfigured": bool(settings.customApiKey)} if engine == "custom" else {}),
        })
    except Exception as exc:
        return _check("integration.tts", "TTS配置", "warn", False, "无法读取TTS配置", {"error": type(exc).__name__})


_check_tts_base = _legacy_check_tts


def check_tts() -> ReadinessCheck:
    result = _check_tts_base()
    engine = result.details.get("selectedEngine")
    if engine == "manbo":
        settings = get_tts_settings_raw()
        missing = []
        if not settings.manboApiKey:
            missing.append("manboApiKey")
        if not settings.manboApiUrl:
            missing.append("manboApiUrl")
        result.details["missingFields"] = missing
    if engine == "none":
        result.message = "已启用纯字幕模式"
        result.details["mode"] = "subtitles_only"
    return result


def check_frontend(*, production_mode: bool, frontend_dist: str | Path | None = None) -> ReadinessCheck:
    dist = Path(frontend_dist).expanduser().resolve() if frontend_dist else resolve_frontend_dist()
    try:
        validate_frontend_dist(dist)
        return _check("runtime.frontend", "前端生产构建", "pass", production_mode, "前端生产构建完整", {"path": str(dist)})
    except Exception as exc:
        return _check("runtime.frontend", "前端生产构建", "fail" if production_mode else "warn", production_mode, "前端生产构建缺失", {"path": str(dist), "error": "build_missing"})


def check_runtime(production_mode: bool, app_name: str = "VideoForge", app_version: str = "0.1.0") -> ReadinessCheck:
    return _check("app.runtime", "应用运行状态", "pass", True, "VideoForge运行正常", {
        "name": app_name, "version": app_version, "productionMode": production_mode,
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
    tts_ok = bool(by_id.get("integration.tts") and by_id["integration.tts"].details.get("voiceoverAvailable"))
    direct_ok = bool(jianying and jianying.status == "pass")
    return {"projectEditing": editing, "voiceover": tts_ok, "previewRendering": editing and ffmpeg_ok,
            "jianyingZipExport": editing, "jianyingDirectExport": editing and direct_ok}


def run_checks(*, production_mode: bool = False, frontend_dist: str | Path | None = None,
               app_name: str = "VideoForge", app_version: str = "0.1.0") -> ReadinessResponse:
    checks = [
        _safe_check(lambda: check_runtime(production_mode, app_name, app_version), "app.runtime", "应用运行状态", True),
        _safe_check(lambda: check_writable_directory(PROJECTS_DIR, "storage.projects", "项目目录", True), "storage.projects", "项目目录", True),
        _safe_check(lambda: check_writable_directory(LIBRARY_DIR, "storage.library", "素材库目录", True), "storage.library", "素材库目录", True),
        _safe_check(lambda: check_writable_directory(TEMP_DIR, "storage.temp", "临时目录", True), "storage.temp", "临时目录", True),
        _safe_check(check_disk, "storage.disk", "磁盘空间"),
        _safe_check(check_ffmpeg, "runtime.ffmpeg", "FFmpeg"),
        _safe_check(check_jianying, "integration.jianying", "剪映草稿目录"),
        _safe_check(check_tts, "integration.tts", "TTS配置"),
        _safe_check(lambda: check_frontend(production_mode=production_mode, frontend_dist=frontend_dist), "runtime.frontend", "前端生产构建", production_mode),
    ]
    status = aggregate_status(checks)
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for item in checks:
        counts[item.status] += 1
    return ReadinessResponse(status=status, checkedAt=datetime.now(timezone.utc),
        app={"name": app_name, "version": app_version, "productionMode": production_mode},
        checks=checks, capabilities=build_capabilities(checks),
        summary={"passed": counts["pass"], "warnings": counts["warn"], "failed": counts["fail"]})


def clear_cache() -> None:
    global _cache
    with _lock:
        _cache = None


def get_readiness(*, refresh: bool = False, production_mode: bool = False,
                  frontend_dist: str | Path | None = None, app_name: str = "VideoForge",
                  app_version: str = "0.1.0") -> ReadinessResponse:
    global _cache
    with _lock:
        now = time.monotonic()
        cache_key = (production_mode, str(Path(frontend_dist).resolve()) if frontend_dist else None, app_name, app_version)
        if not refresh and _cache and now - _cache[0] < TTL_SECONDS and _cache[1] == cache_key:
            return _cache[2]
        result = run_checks(production_mode=production_mode, frontend_dist=frontend_dist, app_name=app_name, app_version=app_version)
        completed_at = time.monotonic()
        _cache = (completed_at, cache_key, result)
        return result
