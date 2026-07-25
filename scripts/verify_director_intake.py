"""Focused smoke test for Director project and SRT intake endpoints."""
from __future__ import annotations

import tempfile
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from services import project_service
from routers import director


class _MemoryStore:
    def __init__(self) -> None:
        self.saved: list[dict] = []

    def save(self, run: dict) -> dict:
        self.saved.append(dict(run))
        return run


class _DirectorSpy:
    def __init__(self) -> None:
        self.store = _MemoryStore()
        self.payloads: list[dict] = []

    def create_run(self, payload: dict) -> dict:
        self.payloads.append(payload)
        return {"runId": "dir_intake", "task": payload["task"]}


def main() -> None:
    from main import create_app

    original_projects_dir = project_service.PROJECTS_DIR
    original_service = director.service
    with tempfile.TemporaryDirectory(prefix="videoforge-director-intake-") as temp:
        project_service.PROJECTS_DIR = Path(temp) / "projects"
        try:
            project = project_service.create_project("Director intake")
            project_service.update_project(project.id, {
                "script": "A structured project script.",
                "subtitles": [{"id": "sub_001", "text": "Hello intake", "start": 0, "end": 1, "style": {}}],
            })
            spy = _DirectorSpy()
            director.service = spy
            client = TestClient(create_app())

            listed = client.get("/api/director/intake/projects")
            assert listed.status_code == 200, listed.text
            assert listed.json()["projects"][0]["id"] == project.id

            inspected = client.get(f"/api/director/intake/projects/{project.id}")
            assert inspected.status_code == 200, inspected.text
            intake = inspected.json()["intake"]
            assert intake["source"]["projectId"] == project.id
            assert intake["subtitleTimeline"][0]["text"] == "Hello intake"

            uploaded = client.post(
                "/api/director/intake/srt",
                files={"file": ("captions.srt", b"1\n00:00:00,000 --> 00:00:01,250\nFirst line\n", "application/x-subrip")},
            )
            assert uploaded.status_code == 200, uploaded.text
            srt_intake = uploaded.json()["intake"]
            assert srt_intake["readiness"]["durationSeconds"] == 1.25
            assert srt_intake["sourceScript"] == "First line"

            started = client.post("/api/director/runs", json={"projectId": project.id, "task": "Plan scenes"})
            assert started.status_code == 200, started.text
            assert "VideoForge Product Constitution v1" in spy.payloads[-1]["task"]
            assert "VideoForge Product Harness context" in spy.payloads[-1]["task"]
            assert spy.store.saved[-1]["intake"]["source"]["projectId"] == project.id

            started_from_srt = client.post("/api/director/runs", json={"intake": srt_intake, "task": "Plan subtitle scenes"})
            assert started_from_srt.status_code == 200, started_from_srt.text
            assert spy.store.saved[-1]["intake"]["source"]["type"] == "srt_upload"
            assert spy.store.saved[-1]["intake"]["subtitleTimeline"][0]["text"] == "First line"
        finally:
            project_service.PROJECTS_DIR = original_projects_dir
            director.service = original_service
    print("director intake verification passed")


if __name__ == "__main__":
    main()
