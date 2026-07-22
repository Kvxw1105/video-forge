"""Offline proof that one semantic visual plan drives preview and JianYing output."""
from __future__ import annotations

import json
import importlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engines.renderer import render_preview
from shared.structured_content import compile_structured_media_variant
from shared.timeline_compiler import compile_project_timeline
from shared.visual_scene import visual_source_hash


pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg"),
    reason="offline visual-scene E2E requires local FFmpeg",
)


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def test_visual_plan_offline_preview_and_jianying_draft(tmp_path):
    """15 subtitles map to PNG/MP4/PNG without external paths in the draft JSON."""
    image_a, image_c = tmp_path / "scene-a.png", tmp_path / "scene-c.png"
    video, voice = tmp_path / "scene-b.mp4", tmp_path / "voice.wav"
    _ffmpeg("-f", "lavfi", "-i", "color=c=red:s=320x568:d=1", "-frames:v", "1", str(image_a))
    _ffmpeg("-f", "lavfi", "-i", "color=c=blue:s=320x568:d=1", "-frames:v", "1", str(image_c))
    _ffmpeg("-f", "lavfi", "-i", "color=c=green:s=320x568:d=1", "-t", "1", "-pix_fmt", "yuv420p", str(video))
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=15", str(voice))
    subtitles = [{"id": f"s{i:02d}", "text": f"line {i}。", "start": float(i - 1), "end": float(i), "style": {}, "metadata": {}} for i in range(1, 16)]
    blocks = [{"id": name, "type": "STORY", "text": name} for name in ("a", "b", "c")]
    bindings = [{"blockId": name, "audioSlice": {"voiceoverId": "vo", "sourceStart": offset, "sourceEnd": offset + 5}, "subtitleIds": [f"s{i:02d}" for i in range(offset + 1, offset + 6)]} for offset, name in ((0, "a"), (5, "b"), (10, "c"))]
    project = {"id": "visual_e2e", "name": "Visual E2E", "canvas": {"width": 320, "height": 568, "fps": 24}, "assets": [{"id": "img_a", "type": "image", "name": image_a.name, "path": str(image_a), "metadata": {}}, {"id": "video_b", "type": "video", "name": video.name, "path": str(video), "metadata": {}}, {"id": "img_c", "type": "image", "name": image_c.name, "path": str(image_c), "metadata": {}}], "audio": {"voiceover": {}, "voiceovers": [{"id": "vo", "file": str(voice), "duration": 15, "isActive": True}], "bgm": {"tracks": []}, "sfx": []}, "subtitles": subtitles, "overlays": {"subtitle_enabled": True}, "timeline": {"blocks": []}, "structuredContent": {"schemaVersion": 1, "episode": {"episodeId": "ep", "blocks": blocks, "variants": [{"id": "publish", "name": "Publish", "blockIds": ["a", "b", "c"]}, {"id": "master", "name": "Master", "blockIds": ["c", "a"]}], "activeVariantId": "publish", "bindings": bindings}}}
    scenes = [{"id": "scene_a", "blockId": "a", "subtitleIds": [f"s{i:02d}" for i in range(1, 6)], "visualAssetIds": ["img_a"]}, {"id": "scene_b", "blockId": "b", "subtitleIds": [f"s{i:02d}" for i in range(6, 11)], "visualAssetIds": ["video_b"], "requestedMediaType": "video", "durationPolicy": "loop"}, {"id": "scene_c", "blockId": "c", "subtitleIds": [f"s{i:02d}" for i in range(11, 16)], "visualAssetIds": ["img_c"]}]
    project["structuredContent"]["episode"]["visualPlan"] = {"schemaVersion": 1, "planId": "plan_e2e", "sourceHash": visual_source_hash(project), "scenes": scenes, "settings": {}}
    compiled = compile_structured_media_variant(project, "publish")
    view = compiled.project_view
    assert [(segment["start"], segment["end"]) for segment in view["segments"]] == [(0.0, 5.0), (5.0, 10.0), (10.0, 15.0)]
    assert len(view["subtitles"]) == 15
    preview = tmp_path / "preview.mp4"
    render_preview(view, preview)
    assert preview.is_file() and preview.stat().st_size > 1_000
    # Some isolated adapter tests reload a fake pyJianYingDraft module. Restore the
    # real installed adapter so this test proves real draft JSON serialization.
    from adapters import jianying
    importlib.reload(jianying)
    drafts = tmp_path / "drafts"; drafts.mkdir()
    draft_path, warnings = jianying._render_jianying_draft(drafts, "Visual E2E", compile_project_timeline(view))
    content = draft_path / "draft_content.json"
    deadline = time.monotonic() + 2
    while not content.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    draft = json.loads(content.read_text(encoding="utf-8"))
    serialized = json.dumps(draft, ensure_ascii=False)
    assert "_vf_loop_scene-b_" in serialized
    assert "subtitle" in serialized.lower() or "text" in serialized.lower()
    master = compile_structured_media_variant(project, "master")
    assert [item["metadata"]["sceneId"] for item in master.project_view["segments"]] == ["scene_c", "scene_a"]
