import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routers import render
from services.jobs import get_job


class FakeProject:
    def __init__(self, voiceover_file: str):
        self.voiceover_file = voiceover_file

    def model_dump(self):
        return {
            "id": "proj_test",
            "canvas": {"width": 1080, "height": 1920, "fps": 30},
            "segments": [{"id": "s1", "assetPath": "", "type": "image", "start": 0, "end": 1}],
            "audio": {
                "voiceover": {"file": self.voiceover_file},
                "voiceovers": [{"id": "vo_1", "file": self.voiceover_file, "isActive": True}],
                "bgm": {"tracks": []},
            },
            "subtitles": [],
            "timeline": {"voiceoverStartAt": 0},
        }


def wait_for_done(job_id: str, timeout: float = 2.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = get_job(job_id)
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not finish: {get_job(job_id)}")


def test_start_generate_preview_returns_job_result(monkeypatch, tmp_path):
    voiceover_path = tmp_path / "voiceover.mp3"
    voiceover_path.write_bytes(b"mp3")

    monkeypatch.setattr(render, "get_project", lambda project_id: FakeProject(str(voiceover_path)))
    monkeypatch.setattr(render, "_project_dir", lambda project_id: tmp_path)
    monkeypatch.setattr(render, "resolve_project_paths", lambda proj_dir, data: data)
    monkeypatch.setattr(render, "_get_mp4_duration", lambda output: 1.0)

    def ok_render(project, output, cue_points=None):
        output.write_bytes(b"mp4")

    monkeypatch.setattr(render, "render_preview", ok_render)

    response = render.start_generate_preview("proj_test")
    assert response["jobId"].startswith("job_")

    result = wait_for_done(response["jobId"])
    assert result["status"] == "succeeded"
    assert result["result"]["previewUrl"].startswith(
        "/api/projects/proj_test/assets/project-file/preview.mp4?v="
    )
