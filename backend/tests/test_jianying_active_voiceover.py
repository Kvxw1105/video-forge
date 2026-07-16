import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters import jianying


def test_active_voiceover_ignores_placeholder_active_entry(tmp_path):
    real = tmp_path / "a.mp3"
    real.write_bytes(b"mp3")
    project = {
        "audio": {
            "voiceover": {"file": "voiceover.mp3", "duration": 0, "text": ""},
            "voiceovers": [
                {"id": "dead", "file": "voiceover.mp3", "duration": 0, "text": "", "isActive": True},
                {"id": "live", "file": str(real), "duration": 1.5, "text": "hi", "isActive": False},
            ],
        }
    }
    # Multi-version mode must not fall back to inactive when active is unplayable.
    active = jianying._active_voiceover(project)
    assert active == {}


def test_active_voiceover_uses_active_playable(tmp_path):
    real = tmp_path / "a.mp3"
    real.write_bytes(b"mp3")
    project = {
        "audio": {
            "voiceovers": [
                {"id": "live", "file": str(real), "duration": 1.5, "text": "hi", "isActive": True},
            ],
        }
    }
    active = jianying._active_voiceover(project)
    assert active.get("id") == "live"


def test_jianying_duration_probe_uses_no_window_helper(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(kwargs)
        class R:
            stdout = '{"streams":[{"duration":"1.25"}]}'
        return R()

    monkeypatch.setattr(jianying, "run_process", fake_run)
    dur = jianying._get_audio_duration(Path("dummy.mp3"))
    assert dur == 1.25
    assert calls, "expected run_process to be used"
