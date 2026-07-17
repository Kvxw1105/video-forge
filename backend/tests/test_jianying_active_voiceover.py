import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters import jianying
from shared.media_probe import probe_media_duration
from shared.voiceover import select_active_voiceover


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
    active = select_active_voiceover(project["audio"])
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
    active = select_active_voiceover(project["audio"])
    assert active.get("id") == "live"


def test_jianying_uses_shared_media_probe():
    assert jianying.probe_media_duration is probe_media_duration
