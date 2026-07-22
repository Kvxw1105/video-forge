"""Offline integration smoke for the structured platform contract."""
import io
import json
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import create_app
from routers import structured_audio
import services.structured_audio_materializer as materializer
from services import project_service
from services.fish_timestamp_tts import ParsedFishTimestamp
from shared.structured_alignment import FishAlignmentSegment


def _wav() -> bytes:
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(8000); output.writeframes(b"\0\0" * 8000)
    return stream.getvalue()


def test_offline_structured_platform_flow(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(materializer, "probe_media_duration", lambda _: 1.0)
    client = TestClient(create_app())
    parsed = client.post("/api/structured/import/parse", json={"text": "# E\n\npreamble\n\n## HOOK\nHook\n\n## STORY\nStory"}).json()
    assert parsed["sections"][0]["sourceHeading"] == "PREAMBLE"
    blocks = [
        {"id": "hook_01", "type": "HOOK", "text": "Hook", "enabled": True},
        {"id": "story_01", "type": "STORY", "text": "Story", "enabled": True},
    ]
    episode = {"episodeId": "ep", "blocks": blocks, "variants": [{"id": "publish", "name": "Publish", "blockIds": ["hook_01", "story_01"]}], "activeVariantId": "publish"}
    created = client.post("/api/projects/structured", json={"name": "E", "episode": episode}).json()
    assert created["audio"]["voiceovers"] == [] and created["subtitles"] == []
    project_id = created["id"]
    project = project_service.get_project(project_id)
    legacy = {"id": "legacy", "file": "legacy.wav", "duration": 1, "isActive": True}
    project_service.update_project(project_id, {"audio": {"voiceover": legacy, "voiceovers": [legacy], "bgm": {"tracks": []}, "sfx": []}})
    state = {"project": project_service.get_project(project_id)}
    parsed_fish = ParsedFishTimestamp(_wav(), (FishAlignmentSegment("Hook", 0, .4, 0), FishAlignmentSegment("Story", .5, 1, 0)), {}, 1)
    monkeypatch.setattr(structured_audio, "get_project", lambda _: state["project"])
    monkeypatch.setattr(structured_audio, "get_tts_settings_raw", lambda: SimpleNamespace(fishApiKey="configured", fishReferenceId="ref", fishModel="s2-pro"))
    monkeypatch.setattr(structured_audio, "request_fish_timestamp", lambda *args, **kwargs: parsed_fish)
    original_update = project_service.update_project
    def persist(pid, data):
        result = original_update(pid, data); state["project"] = result; return result
    monkeypatch.setattr("services.structured_audio_materializer.update_project", persist)
    first = structured_audio.generate_fish_aligned(project_id, {"generateSubtitles": True})
    second = structured_audio.generate_fish_aligned(project_id, {"generateSubtitles": True})
    saved = project_service.get_project(project_id)
    assert first["cached"] is False and second["cached"] is True
    assert saved.audio.voiceover.id == "legacy"
    assert any(item.id == first["voiceoverId"] and not item.isActive for item in saved.audio.voiceovers)
    record = saved.structuredContent.episode.alignment
    assert record and record.inputHash == first["inputHash"]
    assert (tmp_path / project_id / record.audioPath).is_file()
    assert all(binding.audioSlice.voiceoverId == first["voiceoverId"] for binding in saved.structuredContent.episode.bindings)
