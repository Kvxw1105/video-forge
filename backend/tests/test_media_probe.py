import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared import media_probe


def _result(payload: str, returncode: int = 0):
    return SimpleNamespace(returncode=returncode, stdout=payload, stderr="")


def test_probe_prefers_valid_format_duration(monkeypatch):
    calls = []
    monkeypatch.setattr(media_probe, "run_process", lambda cmd, **kwargs: calls.append(cmd) or _result(
        '{"format":{"duration":"4.25"},"streams":[{"duration":"9"}]}'
    ))

    assert media_probe.probe_media_duration("voice.mp3") == 4.25
    assert "-show_format" in calls[0] and "-show_streams" in calls[0]
    assert len(calls) == 1


def test_probe_falls_back_to_largest_valid_stream_duration(monkeypatch):
    monkeypatch.setattr(media_probe, "run_process", lambda *args, **kwargs: _result(
        '{"format":{"duration":"N/A"},"streams":[{"duration":"2.5"},{"duration":"7.5"}]}'
    ))

    assert media_probe.probe_media_duration(Path("video.mp4")) == 7.5


def test_probe_rejects_invalid_json(monkeypatch):
    monkeypatch.setattr(media_probe, "run_process", lambda *args, **kwargs: _result("not-json"))

    assert media_probe.probe_media_duration("bad.mp3") == 0.0


def test_probe_rejects_non_finite_non_positive_durations(monkeypatch):
    monkeypatch.setattr(media_probe, "run_process", lambda *args, **kwargs: _result(
        '{"format":{"duration":"NaN"},"streams":['
        '{"duration":"Infinity"},{"duration":"-1"},{"duration":"0"}]}'
    ))

    assert media_probe.probe_media_duration("bad.mp3") == 0.0


def test_probe_returns_zero_for_ffprobe_failure(monkeypatch):
    monkeypatch.setattr(media_probe, "run_process", lambda *args, **kwargs: _result("{}", returncode=1))

    assert media_probe.probe_media_duration("missing.mp3") == 0.0
