import base64
import copy
import io
import json
import math
import struct
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.project import Project
from routers import structured_audio
from services.fish_timestamp_tts import ParsedFishTimestamp
from shared.structured_alignment import FishAlignmentSegment
import services.structured_audio_materializer as materializer


def make_project(tmp_path):
    return Project.model_validate({"id": "p", "name": "P", "structuredContent": {"schemaVersion": 1, "episode": {"episodeId": "ep", "blocks": [{"id": "a", "type": "STORY", "text": "你好世界"}, {"id": "b", "type": "METHOD", "text": "这是第二段"}], "variants": [], "activeVariantId": None, "bindings": []}}, "audio": {}})


def wav_bytes():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(8000); out.writeframes(b"\0\0" * 8000)
    return buf.getvalue()


def test_missing_key_returns_409(monkeypatch, tmp_path):
    project = make_project(tmp_path)
    monkeypatch.setattr(structured_audio, "get_project", lambda _: project)
    monkeypatch.setattr(structured_audio, "get_tts_settings_raw", lambda: SimpleNamespace(fishApiKey="", fishReferenceId="x"))
    with pytest.raises(Exception) as exc:
        structured_audio.generate_fish_aligned("p", {})
    assert exc.value.status_code == 409


def test_mock_fish_materializes_audio_ranges_subtitles_and_preserves_existing(monkeypatch, tmp_path):
    project = make_project(tmp_path)
    original = copy.deepcopy(project.model_dump())
    parsed = ParsedFishTimestamp(wav_bytes(), (FishAlignmentSegment("你好世界", 0, 0.5, 0), FishAlignmentSegment("这是第二段", 0.6, 1.0, 0)), {}, 1.0)
    monkeypatch.setattr(structured_audio, "get_project", lambda _: project)
    monkeypatch.setattr(structured_audio, "get_tts_settings_raw", lambda: SimpleNamespace(fishApiKey="configured", fishReferenceId="ref", fishModel="s2-pro"))
    monkeypatch.setattr(structured_audio, "request_fish_timestamp", lambda *args, **kwargs: parsed)
    monkeypatch.setattr(structured_audio, "_project_dir", lambda _: tmp_path)
    monkeypatch.setattr(materializer, "update_project", lambda project_id, data: data)
    result = structured_audio.generate_fish_aligned("p", {"generateSubtitles": True})
    assert result["status"] == "ok"
    assert result["blockCount"] == 2
    assert result["subtitleCount"] == 2
    assert Path(result["audioPath"]).read_bytes() == parsed.audio_bytes
    assert Path(result["manifestPath"]).exists()
    assert project.model_dump() == original


def test_status_and_cache_avoid_second_transport_call(monkeypatch, tmp_path):
    project = make_project(tmp_path)
    parsed = ParsedFishTimestamp(wav_bytes(), (FishAlignmentSegment("你好世界", 0, 0.5, 0), FishAlignmentSegment("这是第二段", 0.6, 1.0, 0)), {}, 1.0)
    monkeypatch.setattr(structured_audio, "get_project", lambda _: project)
    monkeypatch.setattr(structured_audio, "get_tts_settings_raw", lambda: SimpleNamespace(fishApiKey="configured", fishReferenceId="ref", fishModel="s2-pro"))
    monkeypatch.setattr(structured_audio, "_project_dir", lambda _: tmp_path)
    monkeypatch.setattr(materializer, "update_project", lambda project_id, data: data)
    calls = []
    monkeypatch.setattr(structured_audio, "request_fish_timestamp", lambda *args, **kwargs: calls.append(1) or parsed)
    first = structured_audio.generate_fish_aligned("p", {})
    second = structured_audio.generate_fish_aligned("p", {})
    assert first["liveCallPerformed"] is True
    assert second["cached"] is True
    assert len(calls) == 1
