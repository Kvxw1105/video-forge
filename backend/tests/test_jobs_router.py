import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routers import jobs
from services.jobs import start_job


def test_get_job_status_returns_snapshot():
    created = start_job("noop", lambda update: {"ok": True})

    status = jobs.get_job_status(created["jobId"])

    assert status["jobId"] == created["jobId"]
    assert status["kind"] == "noop"


def test_get_job_status_404_for_missing_job():
    with pytest.raises(HTTPException) as exc:
        jobs.get_job_status("job_missing")

    assert exc.value.status_code == 404
