from __future__ import annotations

import json
import importlib
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import create_app
from adapters import jianying
from routers import visual_assets
from services import project_service


pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg"),
    reason="code visual motion video preview requires local FFmpeg",
)


def _write_silent_wav(path: Path, duration: float = 2.0, rate: int = 44100) -> None:
    frames = int(duration * rate)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * frames)


def _project_with_code_visual_plan(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(visual_assets, "PROJECTS_DIR", tmp_path)
    project = project_service.create_project("code visual")
    project_dir = tmp_path / project.id
    voice = project_dir / "voice.wav"
    _write_silent_wav(voice, duration=2.0)
    project_service.update_project(project.id, {
        "canvas": {"ratio": "9:16", "width": 270, "height": 480, "fps": 24, "background": {"type": "color", "value": "#000000"}},
        "audio": {
            "voiceover": {"file": "voice.wav", "duration": 2.0},
            "voiceovers": [{"id": "vo", "file": "voice.wav", "duration": 2.0, "isActive": True, "volume": 1.0}],
            "bgm": {"tracks": []},
            "sfx": [],
        },
        "subtitles": [
            {"id": "s1", "text": "code motion", "start": 0.0, "end": 2.0, "style": {}, "metadata": {}},
        ],
        "structuredContent": {
            "schemaVersion": 1,
            "episode": {
                "episodeId": "ep",
                "blocks": [{"id": "story", "type": "STORY", "text": "code motion"}],
                "variants": [{"id": "publish", "name": "Publish", "blockIds": ["story"]}],
                "activeVariantId": "publish",
                "bindings": [{"blockId": "story", "duration": 2.0, "subtitleIds": ["s1"]}],
                "visualPlan": {
                    "schemaVersion": 1,
                    "planId": "plan_code_visual",
                    "sourceHash": "a" * 64,
                    "scenes": [{
                        "id": "scene_code",
                        "blockId": "story",
                        "subtitleIds": ["s1"],
                        "requestedMediaType": "video",
                        "durationPolicy": "loop",
                        "metadata": {"semantic": {"actors": 1, "visualIntent": "evidence", "metadata": {"visualFamily": "evidence"}}},
                    }],
                    "settings": {"mode": "fixed_units", "unitsPerScene": 1},
                },
            },
        },
    })
    return TestClient(create_app()), project.id


def test_code_visual_render_bakes_motion_to_project_video_and_preview(monkeypatch, tmp_path):
    client, project_id = _project_with_code_visual_plan(monkeypatch, tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/visual-assets/code-visual/render",
        json={
            "sourceMode": "visual_plan",
            "exportPng": True,
            "exportVideo": True,
            "videoFps": 6,
            "bindToProject": True,
            "rendererId": "mechanism_diagram",
            "themeMode": "light",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert payload["videoExports"], payload

    project = client.get(f"/api/projects/{project_id}").json()
    asset = next(item for item in project["assets"] if item["id"] == "visual_code_visual_scene_code")
    assert asset["type"] == "video"
    assert asset["metadata"]["motionPlan"]["duration"] >= 2.0
    assert asset["metadata"]["videoSha256"]
    assert (tmp_path / project_id / asset["path"]).is_file()

    scene = project["structuredContent"]["episode"]["visualPlan"]["scenes"][0]
    assert scene["primaryAssetId"] == asset["id"]
    assert scene["visualAssetIds"] == [asset["id"]]

    segment = project["segments"][0]
    assert segment["type"] == "video"
    assert segment["assetPath"] == asset["path"]
    assert segment["start"] == 0.0 and segment["end"] == 2.0

    manifest_path = tmp_path / project_id / payload["manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    item = manifest["items"][0]
    assert item["motionPlanPath"].endswith(".motion.json")
    assert item["videoPath"].endswith(".mp4")
    assert (manifest_path.parent / item["videoPath"]).is_file()

    preview = client.post(f"/api/projects/{project_id}/preview")
    assert preview.status_code == 200, preview.text
    preview_path = tmp_path / project_id / "preview.mp4"
    assert preview_path.is_file() and preview_path.stat().st_size > 1_000
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(preview_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert float(probe.stdout.strip()) >= 2.0

    resolved = project_service.resolve_project_paths(tmp_path / project_id, project_service.get_project(project_id).model_dump())
    importlib.reload(jianying)
    draft = jianying.generate_jianying_draft(
        resolved,
        output_dir=tmp_path / project_id / "jianying",
        policy="create_new",
    )
    content = draft.final_path / "draft_content.json"
    assert content.is_file()
    serialized = content.read_text(encoding="utf-8")
    assert asset["name"] in serialized
