"""End-to-end acceptance for the Stickman provider using a temporary VideoForge project."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from adapters.jianying import generate_jianying_draft
from main import create_app
from routers import visual_assets
from services import project_service
from services.project_service import resolve_project_paths
from shared.structured_content import compile_structured_media_variant


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_silence(path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "3", str(path)],
        check=True,
        capture_output=True,
    )


def _extract_frame(video: Path, at: float, target: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-y", "-ss", str(at), "-i", str(video), "-frames:v", "1", str(target)],
        check=True,
        capture_output=True,
    )


def _pixel_difference(left: Path, right: Path) -> float:
    from PIL import Image, ImageChops, ImageStat

    with Image.open(left).convert("RGB") as a, Image.open(right).convert("RGB") as b:
        return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3


def run() -> dict:
    root = Path(tempfile.mkdtemp(prefix="stickman-acceptance-"))
    projects = root / "projects"
    project_service.PROJECTS_DIR = projects
    visual_assets.PROJECTS_DIR = projects
    project = project_service.create_project("Stickman Acceptance")
    project_dir = projects / project.id
    silence = project_dir / "silence.wav"
    _write_silence(silence)
    project_service.update_project(project.id, {
        "audio": {"voiceover": {}, "voiceovers": [{"id": "voice_1", "file": "silence.wav", "duration": 3, "isActive": True}], "bgm": {"tracks": []}, "sfx": []},
        "subtitles": [
            {"id": "sub_001", "text": "Burden scene!", "start": 0, "end": 1, "style": {}, "metadata": {}},
            {"id": "sub_002", "text": "Control scene!", "start": 1, "end": 2, "style": {}, "metadata": {}},
            {"id": "sub_003", "text": "Conflict scene!", "start": 2, "end": 3, "style": {}, "metadata": {}},
        ],
        "structuredContent": {"schemaVersion": 1, "episode": {
            "episodeId": "stickman_acceptance",
            "blocks": [{"id": "story", "type": "STORY", "text": "acceptance"}],
            "variants": [{"id": "publish", "name": "Publish", "blockIds": ["story"]}],
            "activeVariantId": "publish",
            "bindings": [{"blockId": "story", "audioSlice": {"voiceoverId": "voice_1", "sourceStart": 0, "sourceEnd": 3}, "subtitleIds": ["sub_001", "sub_002", "sub_003"]}],
        }},
    })
    client = TestClient(create_app())
    proposed = client.post(f"/api/projects/{project.id}/visual-plan/propose", json={"mode": "fixed_units", "unitsPerScene": 1}).json()
    scenes = proposed["scenes"]
    semantics = [
        {"topic": "pressure", "actors": 1},
        {"visualIntent": "red_string_pull", "actors": 2},
        {"topic": "inner_conflict", "actors": 2},
    ]
    for scene, semantic in zip(scenes, semantics):
        scene["metadata"] = {"semantic": semantic}
    plan = {"planId": "stickman_plan", "sourceHash": proposed["sourceHash"], "scenes": scenes, "settings": {"mode": "fixed_units", "unitsPerScene": 1}}
    assert client.put(f"/api/projects/{project.id}/visual-plan", json={"plan": plan}).status_code == 200
    rendered = client.post(f"/api/projects/{project.id}/visual-assets/stickman/render", json={"sourceMode": "visual_plan", "exportPng": True, "bindToProject": True})
    assert rendered.status_code == 200, rendered.text
    generation = rendered.json()
    assert generation["status"] == "succeeded"

    preview = client.post(f"/api/projects/{project.id}/structured/variants/publish/preview")
    assert preview.status_code == 200, preview.text
    preview_path = project_dir / "preview_publish.mp4"
    assert preview_path.exists() and preview_path.stat().st_size > 0
    frame_dir = root / "frames"
    frame_dir.mkdir()
    frame_paths = []
    for index, at in enumerate((0.5, 1.5, 2.5), 1):
        frame = frame_dir / f"scene_{index:03d}.png"
        _extract_frame(preview_path, at, frame)
        assert frame.exists() and frame.stat().st_size > 0
        frame_paths.append(frame)
    assert len({_sha256(path) for path in frame_paths}) == 3

    loaded = project_service.get_project(project.id)
    resolved = resolve_project_paths(project_dir, loaded.model_dump())
    compiled = compile_structured_media_variant(resolved, "publish")
    draft = generate_jianying_draft(compiled.project_view, output_dir=root / "jianying", direct_export=True)
    content_path = draft.final_path / "draft_content.json"
    content = content_path.read_text(encoding="utf-8")
    assets = loaded.assets
    for asset in assets:
        assert asset.id.startswith("visual_stickman_")
        assert (project_dir / asset.path).exists()
        assert Path(asset.path).name in content

    before = {asset.id: asset.metadata["pngSha256"] for asset in assets}
    plan_data = loaded.model_dump()["structuredContent"]
    plan_data["episode"]["visualPlan"]["scenes"][1]["metadata"]["semantic"] = {"topic": "comparison", "actors": 2}
    assert client.put(f"/api/projects/{project.id}", json={"structuredContent": plan_data}).status_code == 200
    scene_two = scenes[1]["id"]
    regen = client.post(f"/api/projects/{project.id}/visual-assets/stickman/scenes/{scene_two}/regenerate", json={"exportPng": True})
    assert regen.status_code == 200, regen.text
    after = {asset.id: asset.metadata["pngSha256"] for asset in project_service.get_project(project.id).assets}
    assert before[f"visual_stickman_{scenes[0]['id']}"] == after[f"visual_stickman_{scenes[0]['id']}"]
    assert before[f"visual_stickman_{scenes[2]['id']}"] == after[f"visual_stickman_{scenes[2]['id']}"]
    assert before[f"visual_stickman_{scene_two}"] != after[f"visual_stickman_{scene_two}"]
    rerendered = client.post(f"/api/projects/{project.id}/structured/variants/publish/preview")
    assert rerendered.status_code == 200, rerendered.text
    regenerated_frames = []
    for index, at in enumerate((0.5, 1.5, 2.5), 1):
        frame = frame_dir / f"regenerated_scene_{index:03d}.png"
        _extract_frame(preview_path, at, frame)
        regenerated_frames.append(frame)
    frame_differences = [_pixel_difference(before_frame, after_frame) for before_frame, after_frame in zip(frame_paths, regenerated_frames)]
    assert frame_differences[1] > frame_differences[0] * 3
    assert frame_differences[1] > frame_differences[2] * 3

    subtitle_times = {item["id"]: (item["start"], item["end"]) for item in project_service.get_project(project.id).model_dump()["subtitles"]}
    report = {
        "projectId": project.id,
        "scenes": [{"sceneId": scene["id"], "assetId": f"visual_stickman_{scene['id']}", "start": subtitle_times[scene["subtitleIds"][0]][0], "end": subtitle_times[scene["subtitleIds"][-1]][1], "assetPath": next(asset.path for asset in project_service.get_project(project.id).assets if asset.id == f"visual_stickman_{scene['id']}")} for scene in scenes],
        "previewPath": str(preview_path),
        "frames": [{"time": at, "path": str(path), "bytes": path.stat().st_size} for at, path in zip((0.5, 1.5, 2.5), frame_paths)],
        "jianyingDraft": str(draft.final_path),
        "runId": generation["runId"],
        "regenerate": {"sceneId": scene_two, "before": before[f"visual_stickman_{scene_two}"], "after": after[f"visual_stickman_{scene_two}"], "previewFrames": [str(path) for path in regenerated_frames], "pixelDifferences": frame_differences},
    }
    json_path = root / "acceptance.json"
    markdown_path = root / "acceptance.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text("# Stickman acceptance\n\n" + json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["jsonReport"] = str(json_path)
    report["markdownReport"] = str(markdown_path)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", choices=["full"], default="full")
    args = parser.parse_args()
    print(json.dumps(run(), ensure_ascii=False, indent=2))
