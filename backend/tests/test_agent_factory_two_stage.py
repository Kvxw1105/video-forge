import sys
import pytest
import io, wave
import json
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import template_batch_service as batches
from services import project_service
from routers import structured_audio
import services.structured_audio_materializer as materializer
from services.fish_timestamp_tts import ParsedFishTimestamp
from shared.structured_alignment import FishAlignmentSegment
from fastapi.testclient import TestClient
from main import create_app


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
    calls={"preview":0,"jianying":0}
    def outputs(*args, **kwargs):
        result=kwargs.get("result") or args[-1]; calls["preview"]+=1; calls["jianying"]+=1; result.update({"previewUrl":"/preview.mp4","jianyingDraftPath":"draft","outputs":{"preview":{"status":"succeeded"},"jianying":{"status":"succeeded"}}})
    monkeypatch.setattr(batches,"_run_item_outputs",outputs)
    resumed=client.post(f"/api/agent-factory/batches/{started['batchId']}/items/one/resume",json={})
    assert resumed.status_code==200 and resumed.json()["status"]=="succeeded", resumed.json()
    assert calls=={"preview":1,"jianying":1}
    reused=client.post(f"/api/agent-factory/batches/{started['batchId']}/items/one/resume",json={})
    assert reused.status_code==200 and reused.json()["reused"] is True and calls=={"preview":1,"jianying":1}
