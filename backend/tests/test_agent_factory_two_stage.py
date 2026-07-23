import sys
import pytest
import io, wave
import json
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import template_batch_service as batches
from services import project_service
from services.project_service import resolve_project_paths
from routers import structured_audio
import services.structured_audio_materializer as materializer
from services.fish_timestamp_tts import ParsedFishTimestamp
from shared.structured_alignment import FishAlignmentSegment
from shared.structured_content import compile_structured_media_variant
from fastapi.testclient import TestClient
from main import create_app


def _paused_factory(monkeypatch, tmp_path, *, key="factory_structured_helper"):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(batches, "PROJECTS_DIR", tmp_path)
    raw = io.BytesIO()
    with wave.open(raw, "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000)
        wav.writeframes(b"\0\0" * 8000 * 15)
    sentences = [f"sentence {index}." for index in range(1, 16)]
    parsed = ParsedFishTimestamp(
        raw.getvalue(),
        tuple(FishAlignmentSegment(text, float(index), float(index + 1), 0) for index, text in enumerate(sentences)),
        {}, 15.0,
    )
    monkeypatch.setattr(structured_audio, "get_tts_settings_raw", lambda: SimpleNamespace(fishApiKey="x", fishReferenceId="ref", fishModel="s2-pro"))
    monkeypatch.setattr(structured_audio, "request_fish_timestamp", lambda *args, **kwargs: parsed)
    monkeypatch.setattr(materializer, "probe_media_duration", lambda _: 15.0)
    markdown = "## STORY\n" + "\n".join(sentences[:5]) + "\n\n## MECHANISM\n" + "\n".join(sentences[5:10]) + "\n\n## METHOD\n" + "\n".join(sentences[10:])
    spec = {"schemaVersion": 1, "name": "factory", "idempotencyKey": key, "templateId": "tpl_single_voiceover", "defaults": {"inputMode": "structured_markdown", "voiceover": {"enabled": True, "engine": "fish_audio", "generateSubtitles": True}, "outputs": {"preview": True, "jianyingDirect": True, "jianyingZip": False}}, "visualWorkflow": {"enabled": True, "mode": "generation_pack", "planningMode": "fixed_units", "unitsPerScene": 5, "targetDuration": 5, "minDuration": 1, "maxDuration": 10}, "items": [{"itemId": "one", "name": "One", "structuredMarkdown": markdown, "assets": {"images": [], "videos": [], "bgm": None}}]}
    started = batches.start(spec, lambda *_: {"jobId": "job"})
    batch = batches.execute(started["batchId"])
    row = batch["items"][0]
    assert row["status"] == "awaiting_visual_assets"
    generated = tmp_path / "generated"; generated.mkdir()
    (generated / "scene_001.png").write_bytes(b"png")
    (generated / "scene_002.mp4").write_bytes(b"mp4")
    (generated / "scene_003.png").write_bytes(b"png")
    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(f"/api/agent-factory/batches/{started['batchId']}/items/one/visuals/import", json={"folder": str(generated)})
    assert response.status_code == 200 and response.json()["coverage"]["complete"] is True
    return client, started["batchId"], row, generated


def _output_stub(tmp_path, calls, *, fail_preview=False, fail_jianying=False):
    def run(*args, **kwargs):
        result = kwargs.get("result") or args[-1]
        input_hash = kwargs["input_hash"]
        if not result.get("previewUrl"):
            result["phase"] = "rendering_preview"
            calls["preview"] += 1
            if fail_preview and calls["preview"] == 1:
                raise RuntimeError("preview failed")
            preview = tmp_path / "preview.mp4"; preview.write_bytes(b"preview")
            result["previewUrl"] = "/preview.mp4"
            result.setdefault("outputs", {})["preview"] = {"status": "succeeded", "path": str(preview), "inputHash": input_hash}
        if not result.get("jianyingDraftPath"):
            result["phase"] = "exporting_jianying"
            calls["jianying"] += 1
            if fail_jianying and calls["jianying"] == 1:
                raise RuntimeError("jianying failed")
            draft = tmp_path / "draft"; draft.mkdir(exist_ok=True)
            result["jianyingDraftPath"] = str(draft)
            result.setdefault("outputs", {})["jianying"] = {"status": "succeeded", "draftPath": str(draft), "inputHash": input_hash}
    return run


def test_generation_pack_workflow_requires_real_structured_timing(monkeypatch, tmp_path):
    monkeypatch.setattr(batches, "PROJECTS_DIR", tmp_path)
    spec={"schemaVersion":1,"name":"factory","idempotencyKey":"factory_001","templateId":"tpl_single_voiceover","defaults":{"voiceover":{"enabled":False,"engine":"none"},"outputs":{"preview":False,"jianyingDirect":False,"jianyingZip":False}},"visualWorkflow":{"enabled":True,"mode":"generation_pack"},"items":[{"itemId":"one","name":"One","script":"text","assets":{"images":[],"videos":[],"bgm":None}}]}
    result=batches.plan(spec)
    assert result["errors"][0]["code"] == "generation_pack_requires_structured_input"
    with pytest.raises(batches.BatchError, match="Batch plan"):
        batches.start(spec,lambda *_:{"jobId":"job"})


def test_structured_generation_pack_pauses_after_real_alignment(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service,"PROJECTS_DIR",tmp_path); monkeypatch.setattr(batches,"PROJECTS_DIR",tmp_path)
    raw=io.BytesIO()
    with wave.open(raw,"wb") as wav: wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b"\0\0"*8000*15)
    sentences=[f"sentence {index}." for index in range(1,16)]
    parsed=ParsedFishTimestamp(raw.getvalue(),tuple(FishAlignmentSegment(text,float(index),float(index+1),0) for index,text in enumerate(sentences)),{},15.0)
    monkeypatch.setattr(structured_audio,"get_tts_settings_raw",lambda:SimpleNamespace(fishApiKey="x",fishReferenceId="ref",fishModel="s2-pro"))
    monkeypatch.setattr(structured_audio,"request_fish_timestamp",lambda *args,**kwargs:parsed)
    monkeypatch.setattr(materializer,"probe_media_duration",lambda _:15.0)
    spec={"schemaVersion":1,"name":"factory","idempotencyKey":"factory_structured_001","templateId":"tpl_single_voiceover","defaults":{"inputMode":"structured_markdown","voiceover":{"enabled":True,"engine":"fish_audio","generateSubtitles":True},"outputs":{"preview":True,"jianyingDirect":True,"jianyingZip":False}},"visualWorkflow":{"enabled":True,"mode":"generation_pack","planningMode":"fixed_units","unitsPerScene":5,"targetDuration":5,"minDuration":1,"maxDuration":10},"items":[{"itemId":"one","name":"One","structuredMarkdown":"## STORY\n"+"\n".join(sentences[:5])+"\n\n## MECHANISM\n"+"\n".join(sentences[5:10])+"\n\n## METHOD\n"+"\n".join(sentences[10:]),"assets":{"images":[],"videos":[],"bgm":None}}]}
    started=batches.start(spec,lambda *_:{"jobId":"job"}); result=batches.execute(started["batchId"]); row=result["items"][0]
    assert row["status"]=="awaiting_visual_assets", row["error"]
    assert result["status"]=="awaiting_visual_assets"
    assert len(row["expectedScenes"])==3 and row["previewUrl"] is None and row["jianyingDraftPath"] is None
    project=project_service.get_project(row["projectId"])
    assert len(project.subtitles)==15 and len(project.structuredContent.episode.bindings)==3 and len(project.structuredContent.episode.visualPlan.scenes)==3
    generated=tmp_path/"generated"; generated.mkdir(); (generated/"scene_001.png").write_bytes(b"png"); (generated/"scene_002.mp4").write_bytes(b"mp4")
    client=TestClient(create_app())
    imported=client.post(f"/api/agent-factory/batches/{started['batchId']}/items/one/visuals/import",json={"folder":str(generated)})
    assert imported.status_code==200 and imported.json()["coverage"]["missingScenes"]==["scene_method_01_001"]
    blocked=client.post(f"/api/agent-factory/batches/{started['batchId']}/items/one/resume",json={})
    assert blocked.status_code==409 and blocked.json()["detail"]["code"]=="visual_coverage_incomplete"
    (generated/"scene_003.png").write_bytes(b"png")
    complete=client.post(f"/api/agent-factory/batches/{started['batchId']}/items/one/visuals/import",json={"folder":str(generated)})
    assert complete.status_code==200 and complete.json()["coverage"]["complete"] is True
    project = project_service.get_project(row["projectId"])
    compiled = compile_structured_media_variant(
        resolve_project_paths(tmp_path / row["projectId"], project.model_dump()),
        "publish", duration_resolver=lambda _: 15.0,
    )
    segments = compiled.project_view["segments"]
    assert [(segment["start"], segment["end"], segment["type"]) for segment in segments] == [(0.0, 5.0, "image"), (5.0, 10.0, "video"), (10.0, 15.0, "image")]
    assert compiled.total_duration == 15.0
    assert len(compiled.project_view["subtitles"]) == 15
    calls={"preview":0,"jianying":0}
    def outputs(*args, **kwargs):
        result=kwargs.get("result") or args[-1]; calls["preview"]+=1; calls["jianying"]+=1
        preview_path = tmp_path / "preview.mp4"; preview_path.write_bytes(b"preview")
        draft_path = tmp_path / "draft"; draft_path.mkdir(exist_ok=True)
        result.update({"previewUrl":"/preview.mp4","jianyingDraftPath":str(draft_path),"outputs":{"preview":{"status":"succeeded","path":str(preview_path),"inputHash":kwargs["input_hash"]},"jianying":{"status":"succeeded","draftPath":str(draft_path),"inputHash":kwargs["input_hash"]}}})
    monkeypatch.setattr(batches,"_run_item_outputs",outputs)
    resumed=client.post(f"/api/agent-factory/batches/{started['batchId']}/items/one/resume",json={})
    assert resumed.status_code==200 and resumed.json()["status"]=="succeeded", resumed.json()
    assert calls=={"preview":1,"jianying":1}
    reused=client.post(f"/api/agent-factory/batches/{started['batchId']}/items/one/resume",json={})
    assert reused.status_code==200 and reused.json()["reused"] is True and calls=={"preview":1,"jianying":1}


def test_factory_resume_recovers_only_the_missing_output(monkeypatch, tmp_path):
    client, batch_id, _, _ = _paused_factory(monkeypatch, tmp_path, key="factory_output_recovery")
    calls = {"preview": 0, "jianying": 0}
    monkeypatch.setattr(batches, "_run_item_outputs", _output_stub(tmp_path, calls))
    endpoint = f"/api/agent-factory/batches/{batch_id}/items/one/resume"
    assert client.post(endpoint, json={}).status_code == 200
    batch = batches.get(batch_id); outputs = batch["items"][0]["outputs"]
    preview_path = Path(outputs["preview"]["path"])
    draft_path = Path(outputs["jianying"]["draftPath"])
    assert calls == {"preview": 1, "jianying": 1}
    preview_path.unlink()
    assert client.post(endpoint, json={}).json()["reused"] is False
    assert calls == {"preview": 2, "jianying": 1}
    draft_path.rmdir()
    assert client.post(endpoint, json={}).json()["reused"] is False
    assert calls == {"preview": 2, "jianying": 2}
    final = batches.get(batch_id)["items"][0]
    assert final["status"] == "succeeded"
    assert Path(final["outputs"]["preview"]["path"]).is_file()
    assert Path(final["outputs"]["jianying"]["draftPath"]).is_dir()
    assert final["outputs"]["preview"]["inputHash"] == final["outputs"]["jianying"]["inputHash"]


def test_factory_failure_retries_only_the_failed_phase(monkeypatch, tmp_path):
    client, batch_id, _, _ = _paused_factory(monkeypatch, tmp_path, key="factory_phase_recovery")
    endpoint = f"/api/agent-factory/batches/{batch_id}/items/one/resume"
    calls = {"preview": 0, "jianying": 0}
    monkeypatch.setattr(batches, "_run_item_outputs", _output_stub(tmp_path, calls, fail_jianying=True))
    assert client.post(endpoint, json={}).status_code == 500
    failed = batches.get(batch_id)["items"][0]
    assert failed["status"] == "failed" and failed["phase"] == "exporting_jianying"
    assert calls == {"preview": 1, "jianying": 1}
    assert client.post(endpoint, json={}).status_code == 200
    assert calls == {"preview": 1, "jianying": 2}

    client, batch_id, _, _ = _paused_factory(monkeypatch, tmp_path / "preview-failure", key="factory_preview_recovery")
    endpoint = f"/api/agent-factory/batches/{batch_id}/items/one/resume"
    calls = {"preview": 0, "jianying": 0}
    monkeypatch.setattr(batches, "_run_item_outputs", _output_stub(tmp_path / "preview-failure", calls, fail_preview=True))
    assert client.post(endpoint, json={}).status_code == 500
    failed = batches.get(batch_id)["items"][0]
    assert failed["status"] == "failed" and failed["phase"] == "rendering_preview"
    assert calls == {"preview": 1, "jianying": 0}
    assert client.post(endpoint, json={}).status_code == 200
    assert calls == {"preview": 2, "jianying": 1}


def test_factory_duplicate_import_is_idempotent_and_rejects_conflict(monkeypatch, tmp_path):
    client, batch_id, row, generated = _paused_factory(monkeypatch, tmp_path, key="factory_import_conflict")
    endpoint = f"/api/agent-factory/batches/{batch_id}/items/one/visuals/import"
    before = project_service.get_project(row["projectId"])
    plan_before = before.structuredContent.episode.visualPlan
    duplicate = client.post(endpoint, json={"folder": str(generated)})
    after = project_service.get_project(row["projectId"])
    assert duplicate.status_code == 200 and len(after.assets) == 3
    assert [scene.primaryAssetId for scene in after.structuredContent.episode.visualPlan.scenes] == [scene.primaryAssetId for scene in plan_before.scenes]
    (generated / "scene_001.png").write_bytes(b"different")
    conflict = client.post(endpoint, json={"folder": str(generated)})
    assert conflict.status_code == 409 and conflict.json()["detail"]["code"] == "asset_conflict"
    final = project_service.get_project(row["projectId"])
    assert len(final.assets) == 3
    assert [scene.primaryAssetId for scene in final.structuredContent.episode.visualPlan.scenes] == [scene.primaryAssetId for scene in plan_before.scenes]


def test_factory_rejects_stale_visual_plan_before_outputs(monkeypatch, tmp_path):
    client, batch_id, row, _ = _paused_factory(monkeypatch, tmp_path, key="factory_stale_plan")
    project = project_service.get_project(row["projectId"])
    subtitles = project.model_dump()["subtitles"]
    subtitles[0]["start"] = 0.25
    project_service.update_project(project.id, {"subtitles": subtitles})
    validate = client.post(f"/api/agent-factory/batches/{batch_id}/items/one/visuals/validate", json={})
    resume = client.post(f"/api/agent-factory/batches/{batch_id}/items/one/resume", json={})
    assert validate.status_code == 409 and validate.json()["detail"]["code"] == "visual_plan_stale"
    assert resume.status_code == 409 and resume.json()["detail"]["code"] == "visual_plan_stale"
