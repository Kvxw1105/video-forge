import json
import os
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from main import create_app
from media_processing.contracts import MediaExecutionRequest
from media_processing.native_provider import VideoForgeNativeMediaProvider
from media_processing import service
from services import project_service


def _native_provider():
    ffmpeg_dir = os.environ.get("VIDEOFORGE_MEDIA_FFMPEG_DIR") or os.environ.get("VIDEOFORGE_MEDIAKIT_FFMPEG_DIR")
    if not ffmpeg_dir and (not shutil.which("ffmpeg") or not shutil.which("ffprobe")):
        pytest.skip("FFmpeg integration dependencies are not installed")
    return VideoForgeNativeMediaProvider(ffmpeg_dir=ffmpeg_dir)


def test_native_provider_is_default_and_registers_owned_derivatives(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(service, "PROJECTS_DIR", tmp_path)
    provider = _native_provider()
    discovery = provider.discover()
    assert discovery["provider"] == "videoforge_native"
    assert discovery["installed"] is True
    assert [item["name"] for item in discovery["capabilities"]] == ["media.probe", "video.trim", "audio.extract"]

    project = project_service.create_project("VideoForge native media")
    project_dir = tmp_path / project.id
    source = project_dir / "assets" / "VideoForge 自有能力 with spaces.mp4"
    source.parent.mkdir(exist_ok=True)
    subprocess.check_call([provider.ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=25", "-f", "lavfi", "-i", "sine=frequency=1000", "-t", "2", "-c:v", "mpeg4", "-c:a", "aac", str(source)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=provider._environment())
    project_service.update_project(project.id, {"assets": [{"id": "source", "type": "video", "name": source.name, "path": f"assets/{source.name}", "metadata": {}}]})

    response = TestClient(create_app()).post(f"/api/projects/{project.id}/media/execute", json={"capability": "media.probe", "sourceAssetId": "source"})
    assert response.status_code == 200, response.text
    probe = response.json()
    trimmed = service.execute(project.id, MediaExecutionRequest(capability="video.trim", sourceAssetId="source", startTime=0.2, endTime=1.2))
    audio = service.execute(project.id, MediaExecutionRequest(capability="audio.extract", sourceAssetId="source"))
    assert probe["execution"]["provider"] == "videoforge_native"
    assert probe["execution"]["result"]["video_stream_meta"]["width"] == 160
    assert trimmed["execution"]["status"] == "succeeded"
    assert audio["execution"]["status"] == "succeeded"
    saved = project_service.get_project(project.id).model_dump(mode="python")
    derived = [asset for asset in saved["assets"] if asset["id"] != "source"]
    assert {asset["metadata"]["provider"] for asset in derived} == {"videoforge_native"}
    assert all((project_dir / asset["path"]).exists() for asset in derived)
    record = json.loads((project_dir / trimmed["recordPath"]).read_text(encoding="utf-8"))
    assert record["provider"] == "videoforge_native"


def test_http_provider_registry_defaults_to_videoforge_native():
    response = TestClient(create_app()).get("/api/media/providers")
    assert response.status_code == 200
    payload = response.json()
    assert payload["default"] == "videoforge_native"
    assert [item["provider"] for item in payload["providers"]] == ["videoforge_native", "mediakit"]
