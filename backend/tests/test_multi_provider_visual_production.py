from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import subprocess
import shutil
import importlib
from uuid import uuid4

from services import image_generation_service, project_service
from shared.visual_scene import visual_source_hash
from shared.structured_content import compile_structured_media_variant
from engines.renderer import render_preview
from adapters.jianying import generate_jianying_draft
from visual_providers.code_visual import CodeVisualProvider
from visual_providers.contracts import SceneRequest
from visual_providers.router import route_scene


def _mixed_project(tmp_path, monkeypatch):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    project = project_service.create_project("Mixed provider production", "9:16")
    texts = [
        "人物在心理冲突中做出选择",
        "原因导致结果，解释因果关系",
        "流程分为三个步骤逐步推进",
        "比较两个方案的差异",
        "排名数据从第一名到第四名",
        "知识节点通过网络连接",
    ]
    subtitles = [{"id": f"s{i}", "text": text, "start": i * 2.0, "end": (i + 1) * 2.0} for i, text in enumerate(texts)]
    blocks = [{"id": f"b{i}", "type": "STORY" if i == 0 else "METHOD", "text": text} for i, text in enumerate(texts)]
    structured = {
        "schemaVersion": 1,
        "episode": {
            "episodeId": "mixed_episode",
            "blocks": blocks,
            "variants": [{"id": "publish", "name": "Publish", "blockIds": [block["id"] for block in blocks]}],
            "activeVariantId": "publish",
            "bindings": [{"blockId": f"b{i}", "duration": 2.0, "subtitleIds": [f"s{i}"]} for i in range(len(texts))],
        },
    }
    project = project_service.update_project(project.id, {"subtitles": subtitles, "structuredContent": structured})
    plan = {
        "schemaVersion": 1,
        "planId": "mixed_plan",
        "sourceHash": visual_source_hash(project.model_dump()),
        "scenes": [{"id": f"scene_{i}", "blockId": f"b{i}", "subtitleIds": [f"s{i}"], "summary": text, "prompt": text} for i, text in enumerate(texts)],
        "settings": {"mode": "fixed_units", "unitsPerScene": 1},
    }
    return project_service.update_project(project.id, {"structuredContent": {**project.structuredContent.model_dump(), "episode": {**project.structuredContent.episode.model_dump(), "visualPlan": plan}}})


def _request(text: str, output_mode: str = "static") -> SceneRequest:
    return SceneRequest("p", "plan", "scene", "block", ("s",), text, 0, 2, 2, "a" * 64, "9:16", 270, 480, {"finalPrompt": text, "outputMode": output_mode})


def test_router_covers_stickman_and_code_visual_semantics():
    assert route_scene(_request("人物在关系冲突中做出选择")).provider_id == "stickman"
    assert route_scene(_request("因果关系导致流程结果")).provider_id == "code_visual"
    assert route_scene(_request("未知抽象内容")).provider_id == "stickman"


def test_code_visual_provider_renders_multiple_structured_templates_and_motion():
    provider = CodeVisualProvider()
    templates = ["关键词核心概念", "因果关系导致结果", "流程步骤 progression", "比较 contrast", "排名 data", "节点 topology", "机制 diagram"]
    for index, text in enumerate(templates):
        result = provider.generate(_request(text))
        assert result.success and result.media_type == "image/png"
        assert result.data.startswith(b"\x89PNG")
        assert result.metadata["templateId"]
    motion = provider.generate(_request("流程步骤 progression", "video"))
    if motion.success and motion.media_type != "video/mp4":
        assert motion.media_type == "image/png"
        assert motion.metadata["renderMode"] == "static_fallback"
    elif motion.success:
        assert motion.media_type == "video/mp4"
        assert motion.asset_kind == "video"
        assert motion.duration == 2
        assert motion.duration_policy == "exact"
        assert motion.data[4:8] == b"ftyp"


def test_mixed_provider_batch_routes_candidates_and_binds_assets(tmp_path, monkeypatch):
    project = _mixed_project(tmp_path, monkeypatch)
    batch = image_generation_service.create_batch(project.id, channel="local", routing_mode="auto", candidate_count=1)
    providers = {item["providerId"] for item in batch["items"]}
    assert "stickman" in providers and "code_visual" in providers
    assert all(item["providerVersion"] for item in batch["items"])
    generated = image_generation_service.run_local_batch(project.id, batch["batchId"])
    assert generated["status"] == "awaiting_approval"
    assert all(item["status"] == "generated" for item in generated["items"])
    assert {item["candidates"][0]["mimeType"] for item in generated["items"]} == {"image/png"}
    approved = image_generation_service.approve_candidates(project.id, batch["batchId"], [{"sceneId": item["sceneId"], "candidateId": item["candidates"][0]["candidateId"]} for item in generated["items"]])
    assert approved["batch"]["status"] == "succeeded"
    stored = project_service.get_project(project.id)
    scenes = stored.structuredContent.episode.visualPlan.scenes
    assert all(scene.primaryAssetId for scene in scenes)
    assets = {asset.id: asset for asset in stored.assets}
    assert {assets[scene.primaryAssetId].metadata["provider"] for scene in scenes} == {"stickman", "code_visual"}


def test_local_candidate_count_is_deterministic_and_distinct(tmp_path, monkeypatch):
    project = _mixed_project(tmp_path, monkeypatch)
    batch = image_generation_service.create_batch(
        project.id,
        channel="local",
        routing_mode="code_visual",
        candidate_count=4,
        scene_ids=["scene_1"],
    )
    generated = image_generation_service.run_local_batch(project.id, batch["batchId"])
    item = generated["items"][0]
    assert len(item["candidates"]) == 4
    assert len({candidate["contentHash"] for candidate in item["candidates"]}) == 4
    assert len({candidate["candidateId"] for candidate in item["candidates"]}) == 4
    assert all(candidate["metadata"]["candidateIndex"] == index for index, candidate in enumerate(item["candidates"]))
    assert len({candidate["metadata"]["seed"] for candidate in item["candidates"]}) == 4


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="preview/ffprobe integration requires the optional FFmpeg toolchain",
)
def test_mixed_provider_motion_assets_reach_preview_and_jianying(tmp_path, monkeypatch):
    import adapters.jianying as jianying_adapter
    # Another legacy test reloads this module with a fake pyJianYingDraft
    # runtime. Restore the real adapter before this integration assertion.
    importlib.reload(jianying_adapter)
    project = _mixed_project(tmp_path, monkeypatch)
    overrides = {
        "scene_0": {"providerId": "stickman"},
        "scene_1": {"providerId": "code_visual", "outputMode": "video"},
        "scene_2": {"providerId": "code_visual"},
        "scene_3": {"providerId": "code_visual", "outputMode": "video"},
        "scene_4": {"providerId": "code_visual"},
        "scene_5": {"providerId": "stickman"},
    }
    batch = image_generation_service.create_batch(project.id, channel="local", routing_mode="auto", size="270x480", scene_overrides=overrides)
    generated = image_generation_service.run_local_batch(project.id, batch["batchId"])
    assert generated["status"] == "awaiting_approval"
    media_types = {item["candidates"][0]["mimeType"] for item in generated["items"]}
    assert media_types in ({"image/png"}, {"image/png", "video/mp4"})
    approved = image_generation_service.approve_candidates(project.id, batch["batchId"], [{"sceneId": item["sceneId"], "candidateId": item["candidates"][0]["candidateId"]} for item in generated["items"]])
    assert approved["batch"]["status"] == "succeeded"
    stored = project_service.get_project(project.id)
    resolved = project_service.resolve_project_paths(tmp_path / project.id, stored.model_dump())
    compiled = compile_structured_media_variant(resolved, "publish", duration_resolver=lambda _: 12.0)
    expected_types = {"image", "video"} if "video/mp4" in media_types else {"image"}
    assert {row["type"] for row in compiled.project_view["segments"]} == expected_types
    preview = tmp_path / project.id / "preview-mixed.mp4"
    render_preview(compiled.project_view, preview)
    assert preview.is_file() and preview.stat().st_size > 1000
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(preview)], capture_output=True, text=True, check=True)
    assert float(probe.stdout.strip()) >= 12.0
    jianying_root = Path.cwd() / ".test-artifacts" / f"jianying-{uuid4().hex}"
    try:
        draft = jianying_adapter.generate_jianying_draft(compiled.project_view, output_dir=jianying_root, direct_export=True)
        assert (draft.final_path / "draft_content.json").is_file()
    finally:
        shutil.rmtree(jianying_root.parent, ignore_errors=True)
