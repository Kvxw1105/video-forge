from __future__ import annotations

import logging
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable
from uuid import uuid4

from config import PROJECTS_DIR


JobUpdate = Callable[[float, str, str], None]
JobWork = Callable[[JobUpdate], Any]

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="videoforge-job")
_jobs: dict[str, dict[str, Any]] = {}
_lock = Lock()
logger = logging.getLogger(__name__)
_JOBS_FILE = PROJECTS_DIR / ".jobs.json"


def start_job(kind: str, work: JobWork) -> dict[str, Any]:
    job_id = f"job_{uuid4().hex[:12]}"
    now = _now()
    with _lock:
        _jobs[job_id] = {
            "jobId": job_id,
            "kind": kind,
            "status": "queued",
            "progress": 0,
            "phase": "queued",
            "message": "Queued",
            "result": None,
            "error": None,
            "createdAt": now,
            "updatedAt": now,
        }
        _persist_jobs_locked()
    _executor.submit(_run_job, job_id, work)
    return get_job(job_id)


def get_job(job_id: str) -> dict[str, Any]:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            raise KeyError(job_id)
        return dict(job)


def _run_job(job_id: str, work: JobWork) -> None:
    _set_job(job_id, status="running", progress=1, phase="starting", message="Starting")

    def update(progress: float, phase: str, message: str) -> None:
        safe_progress = max(1, min(99, float(progress)))
        _set_job(job_id, progress=safe_progress, phase=phase, message=message)

    try:
        result = work(update)
    except Exception as exc:
        logger.exception("Background job failed: %s", job_id)
        detail = getattr(exc, "detail", None)
        _set_job(
            job_id,
            status="failed",
            progress=100,
            phase="failed",
            message="Failed",
            error=str(detail or exc),
        )
        return

    _set_job(
        job_id,
        status="succeeded",
        progress=100,
        phase="done",
        message="Done",
        result=result,
    )


def _set_job(job_id: str, **patch: Any) -> None:
    with _lock:
        if job_id not in _jobs:
            return
        _jobs[job_id].update(patch)
        _jobs[job_id]["updatedAt"] = _now()
        _persist_jobs_locked()


def _persist_jobs_locked() -> None:
    _JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = _JOBS_FILE.with_name(f"{_JOBS_FILE.name}.tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(_jobs, handle, ensure_ascii=False, indent=2, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, _JOBS_FILE)
    finally:
        if temp.exists():
            temp.unlink()


def _load_persisted_jobs() -> None:
    if not _JOBS_FILE.exists():
        return
    try:
        persisted = json.loads(_JOBS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.exception("Failed to load persisted jobs from %s", _JOBS_FILE)
        return
    if not isinstance(persisted, dict):
        return

    changed = False
    with _lock:
        for job_id, job in persisted.items():
            if not isinstance(job, dict):
                continue
            restored = dict(job)
            if restored.get("status") in {"queued", "running"}:
                restored.update({
                    "status": "failed",
                    "progress": 100,
                    "phase": "interrupted",
                    "message": "Interrupted by app restart",
                    "error": "Job was interrupted by app restart. Please run it again.",
                    "updatedAt": _now(),
                })
                changed = True
            _jobs[job_id] = restored
        if changed:
            _persist_jobs_locked()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_load_persisted_jobs()
