import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from media_processing.contracts import MediaExecutionRequest
from media_processing.mediakit_provider import MediaKitProvider
from media_processing import service
from services import project_service


FIXTURE = r'''
import json, subprocess, sys
args = sys.argv[1:]
if '--schema' in args:
    print(json.dumps({'input_schema': {'type': 'object'}, 'mode': 'local'})); raise SystemExit(0)
source = args[args.index('--video-url') + 1]
if 'probe-video-metadata' in args:
    raw = subprocess.check_output(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', source])
    print(json.dumps({'metadata': json.loads(raw.decode('utf-8', errors='replace'))})); raise SystemExit(0)
output = args[args.index('--output-path') + 1]
if 'trim-video' in args:
    start = args[args.index('--start-time') + 1]; end = args[args.index('--end-time') + 1]
    subprocess.check_call(['ffmpeg', '-y', '-ss', start, '-to', end, '-i', source, '-c', 'copy', output], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
else:
    subprocess.check_call(['ffmpeg', '-y', '-i', source, '-vn', '-c:a', 'libmp3lame', output], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(json.dumps({'output_path': output, 'status': 'succeeded'}))
'''


def test_mediakit_sidecar_executes_real_media_and_registers_derivatives(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(service, "PROJECTS_DIR", tmp_path)
    official_cli = os.environ.get("VIDEOFORGE_MEDIAKIT_CLI")
    official_ffmpeg = os.environ.get("VIDEOFORGE_MEDIAKIT_FFMPEG_DIR")
    if official_cli and official_ffmpeg:
        provider = MediaKitProvider(official_cli, ffmpeg_dir=official_ffmpeg)
    else:
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            pytest.skip("FFmpeg integration dependencies are not installed")
        fixture = tmp_path / "mediakit fixture.py"
        fixture.write_text(FIXTURE, encoding="utf-8")
        provider = MediaKitProvider([sys.executable, str(fixture)])
    discovered = provider.discover()
    assert discovered["installed"] is True
    schema = discovered["capabilities"][0]["schema"]
    if official_cli and official_ffmpeg:
        assert schema["name"] == "probe_video_metadata"
        assert schema["input_schema"]["required"] == ["video_url"]
    else:
        assert schema["mode"] == "local"

    project = project_service.create_project("MediaKit integration")
    project_dir = tmp_path / project.id
    source = project_dir / "assets" / "source with 中文 name.mp4"
    source.parent.mkdir(exist_ok=True)
    subprocess.check_call(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=25", "-f", "lavfi", "-i", "sine=frequency=1000", "-t", "2", "-c:v", "mpeg4", "-c:a", "aac", str(source)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    project_service.update_project(project.id, {"assets": [{"id": "source", "type": "video", "name": source.name, "path": "assets/source with 中文 name.mp4", "metadata": {}}]})

    probe = service.execute(project.id, MediaExecutionRequest(capability="media.probe", sourceAssetId="source"), provider)
    trimmed = service.execute(project.id, MediaExecutionRequest(capability="video.trim", sourceAssetId="source", startTime=0.2, endTime=1.2), provider)
    audio = service.execute(project.id, MediaExecutionRequest(capability="audio.extract", sourceAssetId="source"), provider)
    assert probe["execution"]["status"] == "succeeded", json.dumps(probe, ensure_ascii=False)
    assert trimmed["execution"]["artifactId"]
    assert audio["execution"]["artifactId"]
    saved = project_service.get_project(project.id).model_dump(mode="python")
    derived = [asset for asset in saved["assets"] if asset["id"] != "source"]
    assert {asset["type"] for asset in derived} == {"video", "audio"}
    assert all((project_dir / asset["path"]).exists() for asset in derived)
    assert all(asset["metadata"]["provider"] == "mediakit" for asset in derived)
    assert json.loads((project_dir / trimmed["recordPath"]).read_text(encoding="utf-8"))["status"] == "succeeded"
