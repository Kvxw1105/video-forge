from __future__ import annotations

import io
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from main import create_app
from services import project_service
from services import template_batch_service as batches
from routers import structured_audio
import services.structured_audio_materializer as materializer
from services.fish_timestamp_tts import ParsedFishTimestamp
from shared.structured_alignment import FishAlignmentSegment
from shared.production_profiles import list_profiles


def _mock_fish(monkeypatch, sentences):
    raw = io.BytesIO()
    with wave.open(raw, "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b"\0\0" * 8000 * len(sentences))
    parsed = ParsedFishTimestamp(raw.getvalue(), tuple(FishAlignmentSegment(text, float(i), float(i + 1), 0) for i, text in enumerate(sentences)), {}, float(len(sentences)))
    monkeypatch.setattr(structured_audio, "get_tts_settings_raw", lambda: type("Settings", (), {"fishApiKey": "x", "fishReferenceId": "ref", "fishModel": "s2-pro"})())
    monkeypatch.setattr(structured_audio, "request_fish_timestamp", lambda *args, **kwargs: parsed)
    monkeypatch.setattr(materializer, "probe_media_duration", lambda _: float(len(sentences)))


def _spec(key: str, mode: str):
    sentences = [f"sentence {i}." for i in range(1, 7)]
    return {
        "schemaVersion": 1,
        "name": "Autonomous V3",
        "idempotencyKey": key,
        "templateId": "tpl_single_voiceover",
        "productionMode": mode,
        "productionProfile": "balanced_auto",
        "defaults": {"inputMode": "structured_markdown", "voiceover": {"enabled": True, "engine": "fish_audio", "generateSubtitles": True}, "outputs": {"preview": True, "jianyingDirect": True, "jianyingZip": False}},
        "visualWorkflow": {"enabled": True, "mode": "generation_pack", "planningMode": "fixed_units", "unitsPerScene": 2, "targetDuration": 2, "minDuration": 1, "maxDuration": 4},
        "items": [{"itemId": "video", "name": "V3 video", "structuredMarkdown": "## STORY\n" + "\n".join(sentences[:3]) + "\n\n## MECHANISM\n" + "\n".join(sentences[3:]), "assets": {"images": [], "videos": [], "bgm": None}}],
    }


def _fake_outputs(tmp_path):
    def run(*args, **kwargs):
        result = kwargs.get("result") or args[-1]
        output_hash = kwargs.get("input_hash")
        preview = tmp_path / "preview.mp4"; preview.write_bytes(b"preview")
        draft = tmp_path / "draft"; draft.mkdir(exist_ok=True); (draft / "draft_content.json").write_text("{}", encoding="utf-8")
        result.update({"previewUrl": "/preview.mp4", "jianyingDraftPath": str(draft), "outputs": {"preview": {"status": "succeeded", "path": str(preview), "inputHash": output_hash}, "jianying": {"status": "succeeded", "draftPath": str(draft), "inputHash": output_hash}}})
    return run


def test_production_profiles_are_thin_policy_objects():
    profiles = {item.id: item for item in list_profiles()}
    assert set(profiles) == {"knowledge_explainer", "psychology_cognition", "balanced_auto"}
    assert profiles["knowledge_explainer"].routingMode == "code_visual"
    assert profiles["psychology_cognition"].routingMode == "stickman"


def test_factory_auto_runs_visual_generation_and_audits_approval(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(batches, "PROJECTS_DIR", tmp_path)
    _mock_fish(monkeypatch, [f"sentence {i}." for i in range(1, 7)])
    monkeypatch.setattr(batches, "_run_item_outputs", _fake_outputs(tmp_path))
    started = batches.start(_spec("v3_auto", "auto"), lambda *_: {"jobId": "job"})
    result = batches.execute(started["batchId"])
    row = result["items"][0]
    assert result["status"] == "succeeded", f"{row.get('errorCode')}: {row.get('error')}"
    assert row["status"] == "succeeded"
    assert row["visualBatchId"]
    assert row["visualCoverage"]["complete"] is True
    visual_batch = Path(tmp_path / row["projectId"] / "image-generation" / "batches" / f"{row['visualBatchId']}.json")
    payload = __import__("json").loads(visual_batch.read_text(encoding="utf-8"))
    assert len(payload["approvalAudit"]) == len(payload["items"])
    assert all(entry["policy"] == "profile:balanced_auto" for entry in payload["approvalAudit"])


def test_factory_review_pauses_then_approve_and_continue(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(batches, "PROJECTS_DIR", tmp_path)
    _mock_fish(monkeypatch, [f"sentence {i}." for i in range(1, 7)])
    monkeypatch.setattr(batches, "_run_item_outputs", _fake_outputs(tmp_path))
    started = batches.start(_spec("v3_review", "review"), lambda *_: {"jobId": "job"})
    paused = batches.execute(started["batchId"])
    row = paused["items"][0]
    assert paused["status"] == "awaiting_visual_approval", f"{row.get('errorCode')}: {row.get('error')}"
    assert row["phase"] == "awaiting_visual_approval"
    client = TestClient(create_app())
    visual_file = tmp_path / row["projectId"] / "image-generation" / "batches" / f"{row['visualBatchId']}.json"
    payload = __import__("json").loads(visual_file.read_text(encoding="utf-8"))
    selections = [{"sceneId": item["sceneId"], "candidateId": item["candidates"][0]["candidateId"]} for item in payload["items"]]
    response = client.post(f"/api/agent-factory/batches/{started['batchId']}/items/video/approve-and-continue", json={"selections": selections})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "succeeded"


def test_incremental_scene_edit_retains_timing_and_other_bindings(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(batches, "PROJECTS_DIR", tmp_path)
    _mock_fish(monkeypatch, [f"sentence {i}." for i in range(1, 7)])
    monkeypatch.setattr(batches, "_run_item_outputs", _fake_outputs(tmp_path))
    started = batches.start(_spec("v3_incremental", "auto"), lambda *_: {"jobId": "job"})
    completed = batches.execute(started["batchId"])
    row = completed["items"][0]
    project_id = row["projectId"]
    before = __import__("services.agent_factory_service", fromlist=["item_visuals"]).item_visuals(started["batchId"], "video")
    first_scene = before["scenes"][0]
    second_scene = before["scenes"][1]
    result = __import__("services.agent_factory_service", fromlist=["edit_scene_and_rerun"]).edit_scene_and_rerun(started["batchId"], "video", first_scene["sceneId"], "edited narration keeps the same timing window")
    assert result["resume"]["status"] == "succeeded"
    after = __import__("services.agent_factory_service", fromlist=["item_visuals"]).item_visuals(started["batchId"], "video")
    edited = next(scene for scene in after["scenes"] if scene["sceneId"] == first_scene["sceneId"])
    retained = next(scene for scene in after["scenes"] if scene["sceneId"] == second_scene["sceneId"])
    assert (edited["start"], edited["end"]) == (first_scene["start"], first_scene["end"])
    assert (retained["start"], retained["end"]) == (second_scene["start"], second_scene["end"])
    assert retained["boundAsset"]
    assert edited["boundAsset"]
    assert after["coverage"]["complete"] is True
    assert len(after["visualBatches"]) >= 2
