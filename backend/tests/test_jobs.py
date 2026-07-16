import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import jobs
from services.jobs import get_job, start_job


def wait_for_done(job_id: str, timeout: float = 2.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = get_job(job_id)
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not finish: {get_job(job_id)}")


def test_job_reports_progress_and_result():
    def work(update):
        update(35, "working", "Copying media")
        return {"path": "draft"}

    job = start_job("export", work)
    result = wait_for_done(job["jobId"])

    assert result["status"] == "succeeded"
    assert result["progress"] == 100
    assert result["phase"] == "done"
    assert result["message"] == "Done"
    assert result["result"] == {"path": "draft"}


def test_job_reports_failure_message():
    def work(update):
        update(20, "render", "Rendering")
        raise RuntimeError("ffmpeg failed")

    job = start_job("preview", work)
    result = wait_for_done(job["jobId"])

    assert result["status"] == "failed"
    assert result["progress"] == 100
    assert result["phase"] == "failed"
    assert "ffmpeg failed" in result["error"]


def test_persisted_running_job_is_marked_interrupted_after_restart(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "_JOBS_FILE", tmp_path / "jobs.json")
    with jobs._lock:
        jobs._jobs.clear()
        jobs._jobs["job_interrupted"] = {
            "jobId": "job_interrupted",
            "kind": "preview",
            "status": "running",
            "progress": 42,
            "phase": "rendering",
            "message": "Rendering",
            "result": None,
            "error": None,
            "createdAt": jobs._now(),
            "updatedAt": jobs._now(),
        }
        jobs._persist_jobs_locked()
        jobs._jobs.clear()

    jobs._load_persisted_jobs()
    restored = jobs.get_job("job_interrupted")

    assert restored["status"] == "failed"
    assert restored["phase"] == "interrupted"
    assert restored["progress"] == 100
    assert "restart" in restored["error"].lower()
