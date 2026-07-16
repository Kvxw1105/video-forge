import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routers import render


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


def test_generate_preview_failure_removes_stale_preview(monkeypatch, tmp_path):
    output_path = tmp_path / "preview.mp4"
    output_path.write_bytes(b"stale")
    voiceover_path = tmp_path / "voiceover.mp3"
    voiceover_path.write_bytes(b"mp3")

    monkeypatch.setattr(render, "get_project", lambda project_id: FakeProject(str(voiceover_path)))
    monkeypatch.setattr(render, "_project_dir", lambda project_id: tmp_path)
    monkeypatch.setattr(render, "resolve_project_paths", lambda proj_dir, data: data)

    def fail_render(project, output, cue_points=None):
        output.write_bytes(b"")
        raise RuntimeError("ffmpeg failed")

    monkeypatch.setattr(render, "render_preview", fail_render)

    with pytest.raises(HTTPException):
        render.generate_preview("proj_test")

    assert not output_path.exists()


def test_generate_preview_returns_cache_busted_url(monkeypatch, tmp_path):
    voiceover_path = tmp_path / "voiceover.mp3"
    voiceover_path.write_bytes(b"mp3")

    monkeypatch.setattr(render, "get_project", lambda project_id: FakeProject(str(voiceover_path)))
    monkeypatch.setattr(render, "_project_dir", lambda project_id: tmp_path)
    monkeypatch.setattr(render, "resolve_project_paths", lambda proj_dir, data: data)
    monkeypatch.setattr(render, "_get_mp4_duration", lambda output: 1.0)

    def ok_render(project, output, cue_points=None):
        output.write_bytes(b"mp4")

    monkeypatch.setattr(render, "render_preview", ok_render)

    result = render.generate_preview("proj_test")

    assert result["previewUrl"].startswith("/api/projects/proj_test/assets/project-file/preview.mp4?v=")


def test_active_voiceover_required_does_not_fallback_when_versions_exist(tmp_path):
    stale_voiceover = tmp_path / "voiceover.mp3"
    stale_voiceover.write_bytes(b"mp3")

    project = {
        "audio": {
            "voiceover": {"file": str(stale_voiceover)},
            "voiceovers": [{"id": "vo_1", "file": str(stale_voiceover), "isActive": False}],
        }
    }

    with pytest.raises(HTTPException) as exc:
        render._require_active_voiceover(project)

    assert exc.value.status_code == 400
