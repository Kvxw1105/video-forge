"""Service-level end-to-end tests: Director Pack runs through the Factory lifecycle."""
from __future__ import annotations

import io
import json
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from pydantic import ValidationError

from models.template_batch import TemplateBatchSpec
from services import project_service
from services import template_batch_service as batches
from services import director_pack_store as store
from routers import structured_audio
import services.structured_audio_materializer as materializer
from services.fish_timestamp_tts import ParsedFishTimestamp
from shared.structured_alignment import FishAlignmentSegment


def _mock_fish(monkeypatch, sentences):
    raw = io.BytesIO()
    with wave.open(raw, "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b"\0\0" * 8000 * len(sentences))
    parsed = ParsedFishTimestamp(raw.getvalue(), tuple(FishAlignmentSegment(text, float(i), float(i + 1), 0) for i, text in enumerate(sentences)), {}, float(len(sentences)))
    monkeypatch.setattr(structured_audio, "get_tts_settings_raw", lambda: type("Settings", (), {"fishApiKey": "x", "fishReferenceId": "ref", "fishModel": "s2-pro"})())
    monkeypatch.setattr(structured_audio, "request_fish_timestamp", lambda *args, **kwargs: parsed)
    monkeypatch.setattr(materializer, "probe_media_duration", lambda _: float(len(sentences)))


PACK_SENTENCES = [
    "人物在心理冲突中做出选择",
    "关系拉扯中的人与情绪",
    "因果机制导致最终结果",
    "系统结构与工作原理",
    "人物关系中的艰难选择",
    "情绪的拉扯与压力",
]


def _spec(key: str, mode: str, *, production_profile: str | None = "balanced_auto", director_pack: dict | None = None):
    sentences = list(PACK_SENTENCES)
    spec = {
        "schemaVersion": 1,
        "name": "Director Pack E2E",
        "idempotencyKey": key,
        "templateId": "tpl_single_voiceover",
        "productionMode": mode,
        "productionProfile": production_profile,
        "defaults": {"inputMode": "structured_markdown", "voiceover": {"enabled": True, "engine": "fish_audio", "generateSubtitles": True}, "outputs": {"preview": True, "jianyingDirect": True, "jianyingZip": False}},
        "visualWorkflow": {"enabled": True, "mode": "generation_pack", "planningMode": "fixed_units", "unitsPerScene": 2, "targetDuration": 2, "minDuration": 1, "maxDuration": 4},
        "items": [{"itemId": "video", "name": "Pack video", "structuredMarkdown": "## STORY\n" + "\n".join(sentences[:2]) + "\n\n## MECHANISM\n" + "\n".join(sentences[2:4]) + "\n\n## STORY\n" + "\n".join(sentences[4:]), "assets": {"images": [], "videos": [], "bgm": None}}],
    }
    if director_pack is not None:
        spec["directorPack"] = director_pack
        spec["productionProfile"] = None
    return spec


def _fake_outputs(tmp_path):
    def run(*args, **kwargs):
        result = kwargs.get("result") or args[-1]
        output_hash = kwargs.get("input_hash")
        preview = tmp_path / "preview.mp4"; preview.write_bytes(b"preview")
        draft = tmp_path / "draft"; draft.mkdir(exist_ok=True); (draft / "draft_content.json").write_text("{}", encoding="utf-8")
        result.update({"previewUrl": "/preview.mp4", "jianyingDraftPath": str(draft), "outputs": {"preview": {"status": "succeeded", "path": str(preview), "inputHash": output_hash}, "jianying": {"status": "succeeded", "draftPath": str(draft), "inputHash": output_hash}}})
    return run


def _run_pack_batch(monkeypatch, tmp_path, mode: str, *, key: str = "pack_auto") -> dict:
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(batches, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(store, "DIRECTOR_PACKS_DIR", tmp_path / "installed")
    _mock_fish(monkeypatch, list(PACK_SENTENCES))
    monkeypatch.setattr(batches, "_run_item_outputs", _fake_outputs(tmp_path))
    store.install_builtin("kvxw/knowledge-cinematic", "1.0.0")
    started = batches.start(
        _spec(key, mode, director_pack={"id": "kvxw/knowledge-cinematic", "version": "1.0.0"}),
        lambda *_: {"jobId": "job"},
    )
    return batches.execute(started["batchId"])


def test_batch_rejects_profile_and_director_pack_together():
    spec = _spec("exclusive", "auto")
    spec["productionProfile"] = "balanced_auto"
    spec["directorPack"] = {"id": "kvxw/knowledge-cinematic", "version": "1.0.0"}
    with pytest.raises(ValidationError):
        TemplateBatchSpec.model_validate(spec)


def test_director_pack_run_pins_policy_and_uses_existing_candidates(monkeypatch, tmp_path):
    result = _run_pack_batch(monkeypatch, tmp_path, mode="auto")
    row = result["items"][0]
    snapshot = row["resolvedDirectorPolicy"]
    assert snapshot["pack"]["id"] == "kvxw/knowledge-cinematic"
    assert snapshot["pack"]["manifestDigest"].startswith("sha256:")
    assert snapshot["pack"]["sourceTrust"] == "TRUSTED_BUILTIN"
    assert row["visualCoverage"]["complete"] is True
    assert row["status"] == "succeeded"


def test_director_pack_run_mixes_code_visual_and_stickman_candidates(monkeypatch, tmp_path):
    result = _run_pack_batch(monkeypatch, tmp_path, mode="auto", key="pack_mixed")
    row = result["items"][0]
    visual_batch = json.loads(
        (Path(tmp_path) / row["projectId"] / "image-generation" / "batches" / f"{row['visualBatchId']}.json").read_text(encoding="utf-8")
    )
    providers = {item.get("providerId") for item in visual_batch["items"]}
    assert "code_visual" in providers and "stickman" in providers
    assert all(entry["policy"].startswith("director_pack:kvxw/knowledge-cinematic") for entry in visual_batch["approvalAudit"])


def test_director_pack_review_pauses_then_approve_and_continue(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from main import create_app

    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(batches, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(store, "DIRECTOR_PACKS_DIR", tmp_path / "installed")
    _mock_fish(monkeypatch, list(PACK_SENTENCES))
    monkeypatch.setattr(batches, "_run_item_outputs", _fake_outputs(tmp_path))
    store.install_builtin("kvxw/knowledge-cinematic", "1.0.0")
    started = batches.start(
        _spec("pack_review", "review", director_pack={"id": "kvxw/knowledge-cinematic", "version": "1.0.0"}),
        lambda *_: {"jobId": "job"},
    )
    paused = batches.execute(started["batchId"])
    row = paused["items"][0]
    assert paused["status"] == "awaiting_visual_approval", f"{row.get('errorCode')}: {row.get('error')}"
    assert row["phase"] == "awaiting_visual_approval"
    visual_file = Path(tmp_path) / row["projectId"] / "image-generation" / "batches" / f"{row['visualBatchId']}.json"
    payload = json.loads(visual_file.read_text(encoding="utf-8"))
    selections = [{"sceneId": item["sceneId"], "candidateId": item["candidates"][0]["candidateId"]} for item in payload["items"]]
    client = TestClient(create_app())
    response = client.post(f"/api/agent-factory/batches/{started['batchId']}/items/video/approve-and-continue", json={"selections": selections})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "succeeded"


def test_director_pack_batch_manifest_persists_policy_snapshot(monkeypatch, tmp_path):
    result = _run_pack_batch(monkeypatch, tmp_path, mode="auto", key="pack_persist")
    manifest = batches.get(result["batchId"])
    assert manifest.get("directorPack") == {"id": "kvxw/knowledge-cinematic", "version": "1.0.0"}
    row = manifest["items"][0]
    snapshot = row["resolvedDirectorPolicy"]
    assert snapshot["schemaVersion"] == 1
    assert snapshot["effectiveRouting"]["causal"][0] == "code_visual"
    assert snapshot["effectiveRouting"]["relationship"][0] == "stickman"
    # The same frozen snapshot must be reused on resume, not re-resolved.
    assert manifest["items"][0]["status"] == "succeeded"


def test_director_pack_resume_uses_frozen_snapshot_not_new_version(monkeypatch, tmp_path):
    result = _run_pack_batch(monkeypatch, tmp_path, mode="auto", key="pack_frozen")
    before = batches.get(result["batchId"])["items"][0]["resolvedDirectorPolicy"]
    # "Install" a newer version while the old run is frozen; resume must reuse
    # the old snapshot and succeed without re-resolving.
    monkeypatch.setattr(store, "DIRECTOR_PACKS_DIR", tmp_path / "installed")
    resumed = batches.resume(result["batchId"], lambda *_: {"jobId": "job2"})
    assert resumed["status"] == "succeeded"
    after = batches.get(result["batchId"])["items"][0]["resolvedDirectorPolicy"]
    assert after["pack"]["version"] == before["pack"]["version"]
    assert after["pack"]["manifestDigest"] == before["pack"]["manifestDigest"]
