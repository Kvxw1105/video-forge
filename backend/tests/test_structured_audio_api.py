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


@pytest.fixture(autouse=True)
def _probe_generated_test_wav(monkeypatch):
    """Fish transaction tests exercise filesystem semantics, not ffprobe."""
    monkeypatch.setattr(materializer, "probe_media_duration", lambda _: 1.0)


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
    saved = []
    monkeypatch.setattr(materializer, "update_project", lambda project_id, data: saved.append(data) or data)
    result = structured_audio.generate_fish_aligned("p", {"generateSubtitles": True})
    assert result["status"] == "ok"
    assert result["blockCount"] == 2
    assert result["subtitleCount"] == 2
    assert (tmp_path / result["audioPath"]).read_bytes() == parsed.audio_bytes
    assert (tmp_path / result["manifestPath"]).exists()
    assert project.model_dump() == original
    assert not Path(saved[0]["audio"]["voiceover"]["file"]).is_absolute()


def test_status_and_cache_avoid_second_transport_call(monkeypatch, tmp_path):
    project = make_project(tmp_path)
    parsed = ParsedFishTimestamp(wav_bytes(), (FishAlignmentSegment("你好世界", 0, 0.5, 0), FishAlignmentSegment("这是第二段", 0.6, 1.0, 0)), {}, 1.0)
    state = {"project": project}
    monkeypatch.setattr(structured_audio, "get_project", lambda _: state["project"])
    monkeypatch.setattr(structured_audio, "get_tts_settings_raw", lambda: SimpleNamespace(fishApiKey="configured", fishReferenceId="ref", fishModel="s2-pro"))
    monkeypatch.setattr(structured_audio, "_project_dir", lambda _: tmp_path)
    monkeypatch.setattr(materializer, "update_project", lambda project_id, data: state.__setitem__("project", Project.model_validate(data)) or state["project"])
    calls = []
    monkeypatch.setattr(structured_audio, "request_fish_timestamp", lambda *args, **kwargs: calls.append(1) or parsed)
    first = structured_audio.generate_fish_aligned("p", {})
    second = structured_audio.generate_fish_aligned("p", {})
    assert first["liveCallPerformed"] is True
    assert second["cached"] is True
    assert len(calls) == 1


def test_cache_misses_when_input_changes_or_is_forced(monkeypatch, tmp_path):
    project = make_project(tmp_path)
    parsed = ParsedFishTimestamp(wav_bytes(), (FishAlignmentSegment("\u4f60\u597d\u4e16\u754c", 0, 0.5, 0), FishAlignmentSegment("\u8fd9\u662f\u7b2c\u4e8c\u6bb5", 0.6, 1.0, 0)), {}, 1.0)
    state = {"project": project}
    monkeypatch.setattr(structured_audio, "get_project", lambda _: state["project"])
    monkeypatch.setattr(structured_audio, "get_tts_settings_raw", lambda: SimpleNamespace(fishApiKey="configured", fishReferenceId="ref", fishModel="s2-pro"))
    monkeypatch.setattr(structured_audio, "_project_dir", lambda _: tmp_path)
    monkeypatch.setattr(materializer, "update_project", lambda _, data: state.__setitem__("project", Project.model_validate(data)) or state["project"])
    calls = []
    monkeypatch.setattr(structured_audio, "request_fish_timestamp", lambda *args, **kwargs: calls.append(kwargs) or parsed)
    assert not structured_audio.generate_fish_aligned("p", {})["cached"]
    assert structured_audio.generate_fish_aligned("p", {})["cached"]
    assert not structured_audio.generate_fish_aligned("p", {"speed": 1.2})["cached"]
    assert not structured_audio.generate_fish_aligned("p", {"force": True})["cached"]
    assert len(calls) == 3


def test_project_save_failure_removes_only_new_generation(monkeypatch, tmp_path):
    project = make_project(tmp_path).model_dump()
    history = tmp_path / "structured" / "fish" / "previous"
    history.mkdir(parents=True)
    (history / "master_voice.wav").write_bytes(b"historical")
    parsed = ParsedFishTimestamp(wav_bytes(), (FishAlignmentSegment("\u4f60\u597d\u4e16\u754c", 0, 0.5, 0), FishAlignmentSegment("\u8fd9\u662f\u7b2c\u4e8c\u6bb5", 0.6, 1.0, 0)), {}, 1.0)
    monkeypatch.setattr(materializer, "probe_media_duration", lambda _: 1.0)
    monkeypatch.setattr(materializer, "update_project", lambda *_: (_ for _ in ()).throw(OSError("save failed")))
    with pytest.raises(OSError, match="save failed"):
        materializer.materialize_structured_audio("p", project, parsed, project_dir=tmp_path, options={"referenceId": "ref"})
    assert (history / "master_voice.wav").read_bytes() == b"historical"
    assert not list((tmp_path / "structured" / "fish").glob("*.staging"))
    assert [path.name for path in (tmp_path / "structured" / "fish").iterdir()] == ["previous"]


@pytest.mark.parametrize("kind, expected", [("audio", "audio_missing"), ("manifest", "manifest_missing"), ("binding", "binding_mismatch"), ("subtitle", "subtitle_mismatch")])
def test_cache_reports_precise_corruption_reason(monkeypatch, tmp_path, kind, expected):
    project = make_project(tmp_path)
    parsed = ParsedFishTimestamp(wav_bytes(), (FishAlignmentSegment("\u4f60\u597d\u4e16\u754c", 0, 0.5, 0), FishAlignmentSegment("\u8fd9\u662f\u7b2c\u4e8c\u6bb5", 0.6, 1.0, 0)), {}, 1.0)
    state = {"project": project}
    monkeypatch.setattr(structured_audio, "get_project", lambda _: state["project"])
    monkeypatch.setattr(structured_audio, "get_tts_settings_raw", lambda: SimpleNamespace(fishApiKey="configured", fishReferenceId="ref", fishModel="s2-pro"))
    monkeypatch.setattr(structured_audio, "_project_dir", lambda _: tmp_path)
    monkeypatch.setattr(materializer, "update_project", lambda _, data: state.__setitem__("project", Project.model_validate(data)) or state["project"])
    monkeypatch.setattr(structured_audio, "request_fish_timestamp", lambda *args, **kwargs: parsed)
    first = structured_audio.generate_fish_aligned("p", {})
    current = state["project"].model_dump()
    record = current["structuredContent"]["episode"]["alignment"]
    if kind == "audio":
        (tmp_path / record["audioPath"]).unlink()
    elif kind == "manifest":
        (tmp_path / record["manifestPath"]).unlink()
    elif kind == "binding":
        current["structuredContent"]["episode"]["bindings"][0]["audioSlice"]["sourceEnd"] = 99
        state["project"] = Project.model_validate(current)
    else:
        current["subtitles"] = []
        state["project"] = Project.model_validate(current)
    result = structured_audio.generate_fish_aligned("p", {})
    assert result["cached"] is False
    assert result["cacheStatus"] == expected


def test_generation_rejects_project_change_before_materialization(monkeypatch, tmp_path):
    project = make_project(tmp_path)
    parsed = ParsedFishTimestamp(wav_bytes(), (FishAlignmentSegment("\u4f60\u597d\u4e16\u754c", 0, 0.5, 0), FishAlignmentSegment("\u8fd9\u662f\u7b2c\u4e8c\u6bb5", 0.6, 1.0, 0)), {}, 1.0)
    state = {"project": project}
    monkeypatch.setattr(structured_audio, "get_project", lambda _: state["project"])
    monkeypatch.setattr(structured_audio, "get_tts_settings_raw", lambda: SimpleNamespace(fishApiKey="configured", fishReferenceId="ref", fishModel="s2-pro"))
    monkeypatch.setattr(structured_audio, "_project_dir", lambda _: tmp_path)

    def mutate_then_return(*args, **kwargs):
        changed = state["project"].model_dump()
        changed["updated_at"] = "2099-01-01T00:00:00"
        changed["structuredContent"]["episode"]["blocks"][0]["text"] = "changed"
        state["project"] = Project.model_validate(changed)
        return parsed

    monkeypatch.setattr(structured_audio, "request_fish_timestamp", mutate_then_return)
    with pytest.raises(Exception) as exc:
        structured_audio.generate_fish_aligned("p", {"expectedUpdatedAt": project.updated_at})
    assert exc.value.status_code == 409
    assert exc.value.detail == "structured_project_changed_during_generation"
    assert not (tmp_path / "structured").exists()
