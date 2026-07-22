import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import create_app
from services import project_service


def test_visual_context_and_conflict(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    project = project_service.create_project("visual")
    voice = tmp_path / project.id / "voice.wav"; voice.write_bytes(b"wav")
    project_service.update_project(project.id, {"audio":{"voiceover":{},"voiceovers":[{"id":"vo","file":"voice.wav","duration":2,"isActive":False}],"bgm":{"tracks":[]},"sfx":[]},"subtitles":[{"id":"s1","text":"hello。","start":0,"end":2,"style":{},"metadata":{}}],"structuredContent":{"schemaVersion":1,"episode":{"episodeId":"ep","blocks":[{"id":"story","type":"STORY","text":"hello"}],"variants":[{"id":"publish","name":"Publish","blockIds":["story"]}],"activeVariantId":"publish","bindings":[{"blockId":"story","audioSlice":{"voiceoverId":"vo","sourceStart":0,"sourceEnd":2},"subtitleIds":["s1"]}]}}})
    client=TestClient(create_app()); context=client.get(f"/api/projects/{project.id}/visual-plan/context")
    assert context.status_code == 200 and context.json()["blocks"][0]["narrationUnits"][0]["subtitleIds"] == ["s1"]
    proposed=client.post(f"/api/projects/{project.id}/visual-plan/propose",json={"mode":"fixed_units","unitsPerScene":1}).json()
    plan={"planId":"plan_1","sourceHash":proposed["sourceHash"],"scenes":proposed["scenes"],"settings":{"mode":"fixed_units","unitsPerScene":1}}
    saved=client.put(f"/api/projects/{project.id}/visual-plan",json={"plan":plan,"expectedUpdatedAt":project_service.get_project(project.id).updated_at})
    assert saved.status_code == 200
    assert client.post(f"/api/projects/{project.id}/visual-plan/validate",json={}).json()["valid"] is True


def test_visual_folder_import_copies_project_relative_asset(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    project = project_service.create_project("visual import")
    voice = tmp_path / project.id / "voice.wav"; voice.write_bytes(b"wav")
    project_service.update_project(project.id, {"audio":{"voiceover":{},"voiceovers":[{"id":"vo","file":"voice.wav","duration":1,"isActive":False}],"bgm":{"tracks":[]},"sfx":[]},"subtitles":[{"id":"s1","text":"line。","start":0,"end":1,"style":{},"metadata":{}}],"structuredContent":{"schemaVersion":1,"episode":{"episodeId":"ep","blocks":[{"id":"story","type":"STORY","text":"line"}],"variants":[{"id":"publish","name":"Publish","blockIds":["story"]}],"activeVariantId":"publish","bindings":[{"blockId":"story","audioSlice":{"voiceoverId":"vo","sourceStart":0,"sourceEnd":1},"subtitleIds":["s1"]}]}}})
    client=TestClient(create_app()); proposed=client.post(f"/api/projects/{project.id}/visual-plan/propose",json={"mode":"fixed_units","unitsPerScene":1}).json()
    client.put(f"/api/projects/{project.id}/visual-plan",json={"plan":{"planId":"plan_import","sourceHash":proposed["sourceHash"],"scenes":proposed["scenes"],"settings":{"mode":"fixed_units"}}})
    source=tmp_path/"generated"; source.mkdir(); (source/"scene_story_001.png").write_bytes(b"png")
    response=client.post(f"/api/projects/{project.id}/visual-plan/import-folder",json={"folder":str(source)})
    assert response.status_code == 200 and response.json()["imported"] == ["scene_story_001"]
    saved=project_service.get_project(project.id)
    assert saved.assets[0].path.startswith("assets/") and not Path(saved.assets[0].path).is_absolute()


def test_generation_pack_has_subtitle_derived_timing_and_manifest_import(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    project = project_service.create_project("visual pack")
    voice = tmp_path / project.id / "voice.wav"; voice.write_bytes(b"wav")
    project_service.update_project(project.id, {"audio":{"voiceover":{},"voiceovers":[{"id":"vo","file":"voice.wav","duration":2,"isActive":False}],"bgm":{"tracks":[]},"sfx":[]},"subtitles":[{"id":"s1","text":"first。","start":0,"end":1,"style":{},"metadata":{}},{"id":"s2","text":"second。","start":1,"end":2,"style":{},"metadata":{}}],"structuredContent":{"schemaVersion":1,"episode":{"episodeId":"ep","blocks":[{"id":"story","type":"STORY","text":"text"}],"variants":[{"id":"publish","name":"Publish","blockIds":["story"]}],"activeVariantId":"publish","bindings":[{"blockId":"story","audioSlice":{"voiceoverId":"vo","sourceStart":0,"sourceEnd":2},"subtitleIds":["s1","s2"]}]}}})
    client = TestClient(create_app())
    proposed = client.post(f"/api/projects/{project.id}/visual-plan/propose", json={"mode":"fixed_units", "unitsPerScene":1}).json()
    plan = {"planId":"plan_pack", "sourceHash":proposed["sourceHash"], "scenes":proposed["scenes"], "settings":{"mode":"fixed_units"}}
    assert client.put(f"/api/projects/{project.id}/visual-plan", json={"plan":plan}).status_code == 200
    packed = client.post(f"/api/projects/{project.id}/visual-plan/generation-pack")
    assert packed.status_code == 200
    prompts = __import__("json").loads((Path(packed.json()["path"]) / "prompts.json").read_text(encoding="utf-8"))
    assert [(row["start"], row["end"], row["duration"], row["text"]) for row in prompts] == [(0.0, 1.0, 1.0, "first。"), (1.0, 2.0, 1.0, "second。")]
    source = tmp_path / "ai.png"; source.write_bytes(b"png")
    imported = client.post(f"/api/projects/{project.id}/visual-plan/import-folder", json={"manifest":{"scene_story_001":str(source)}})
    assert imported.status_code == 200 and imported.json()["imported"] == ["scene_story_001"]
