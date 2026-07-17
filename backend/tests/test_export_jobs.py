import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routers import export
from services.jobs import get_job


class FakeProject:
    name = "Test Project"

    def __init__(self, voiceover_file: str):
        self.voiceover_file = voiceover_file

    def model_dump(self):
        return {
            "id": "proj_test",
            "segments": [{"id": "s1", "assetPath": "", "type": "image", "start": 0, "end": 1}],
            "audio": {
                "voiceover": {"file": self.voiceover_file},
                "voiceovers": [{"id": "vo_1", "file": self.voiceover_file, "isActive": True}],
                "bgm": {"tracks": []},
            },
            "subtitles": [],
        }


def wait_for_done(job_id: str, timeout: float = 2.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = get_job(job_id)
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not finish: {get_job(job_id)}")


def test_start_export_jianying_direct_returns_job_result(monkeypatch, tmp_path):
    voiceover_path = tmp_path / "voiceover.mp3"
    voiceover_path.write_bytes(b"mp3")
    draft_dir = tmp_path / "draft_1"
    draft_dir.mkdir()

    monkeypatch.setattr(export, "JIANYING_DRAFT_DIR", tmp_path)
    monkeypatch.setattr(export, "get_project", lambda project_id: FakeProject(str(voiceover_path)))
    monkeypatch.setattr(export, "_project_dir", lambda project_id: tmp_path)
    monkeypatch.setattr(export, "resolve_project_paths", lambda proj_dir, data: data)
    monkeypatch.setattr(
        export,
        "generate_jianying_draft",
        lambda project, output_dir=None, cue_points=None, **kwargs: SimpleNamespace(
            to_metadata=lambda: {"draftName": draft_dir.name, "finalPath": str(draft_dir)},
        ),
    )

    response = export.start_export_jianying_direct("proj_test")
    assert response["jobId"].startswith("job_")

    result = wait_for_done(response["jobId"])
    assert result["status"] == "succeeded"
    assert result["result"]["status"] == "ok"
    assert result["result"]["draft_name"] == "draft_1"


def test_zip_export_rejects_replace_explicit_policy():
    with pytest.raises(HTTPException, match="replace_explicit is only supported by direct JianYing export") as error:
        export.export_jianying("proj_test", policy="replace_explicit")

    assert error.value.status_code == 400


def test_zip_export_returns_safe_draft_metadata_headers(monkeypatch, tmp_path):
    voiceover_path = tmp_path / "voiceover.mp3"
    voiceover_path.write_bytes(b"mp3")
    draft_dir = tmp_path / "draft_1"
    draft_dir.mkdir()
    (draft_dir / "draft_content.json").write_bytes(b"draft")

    monkeypatch.setattr(export, "get_project", lambda project_id: FakeProject(str(voiceover_path)))
    monkeypatch.setattr(export, "_project_dir", lambda project_id: tmp_path)
    monkeypatch.setattr(export, "resolve_project_paths", lambda proj_dir, data: data)
    monkeypatch.setattr(
        export,
        "generate_jianying_draft",
        lambda *args, **kwargs: SimpleNamespace(
            final_path=draft_dir,
            policy="create_new",
            revision=3,
        ),
    )

    response = export.export_jianying("proj_test")

    assert response.headers["X-VideoForge-Policy"] == "create_new"
    assert response.headers["X-VideoForge-Draft-Name"] == "draft_1"
    assert response.headers["X-VideoForge-Revision"] == "3"
    assert "X-VideoForge-Final-Path" not in response.headers


def test_internal_backup_directory_is_not_listed_as_a_user_draft(monkeypatch, tmp_path):
    visible = tmp_path / "Visible Draft"
    visible.mkdir()
    (visible / "draft_content.json").write_bytes(b"visible")
    backup = tmp_path / ".videoforge-backups" / "Visible Draft-backup"
    backup.mkdir(parents=True)
    (backup / "draft_content.json").write_bytes(b"backup")
    monkeypatch.setattr(export, "JIANYING_DRAFT_DIR", tmp_path)

    drafts = export._list_jianying_drafts()

    assert [draft["folder"] for draft in drafts] == ["Visible Draft"]
