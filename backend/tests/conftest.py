import pytest


@pytest.fixture(autouse=True)
def isolate_job_persistence(monkeypatch, tmp_path):
    from services import jobs

    monkeypatch.setattr(jobs, "_JOBS_FILE", tmp_path / "jobs.json")
