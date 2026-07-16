"""Smoke tests for timeline block data model.
Run from repo root: python scripts/test_timeline_blocks.py
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from models.project import Project  # noqa: E402


def test_timeline_blocks_and_audio_offsets():
    project = Project(
        timeline={
            "voiceoverStartAt": 1.5,
            "blocks": [
                {"type": "black", "duration": 1.5, "bgColor": "#000000"},
                {"type": "assets", "duration": 12, "source": "videos", "mode": "random", "perAssetDuration": 1.0},
                {"type": "assets", "duration": "rest", "source": "images", "mode": "ordered", "perAssetDuration": 2.0},
            ],
        },
        audio={
            "bgm": {"tracks": [{"file": "bgm.mp3", "startAt": 3.0, "trimStart": 10.0, "trimEnd": 30.0}]},
            "sfx": [{"file": "whoosh.mp3", "startAt": 1.5, "volume": 0.8}],
        },
    )

    assert project.timeline.voiceoverStartAt == 1.5
    assert len(project.timeline.blocks) == 3
    assert project.timeline.blocks[0].type == "black"
    assert project.timeline.blocks[2].duration == "rest"
    assert project.audio.bgm.tracks[0].startAt == 3.0
    assert project.audio.sfx[0].file == "whoosh.mp3"
    assert project.audio.sfx[0].startAt == 1.5


if __name__ == "__main__":
    test_timeline_blocks_and_audio_offsets()
    print("PASS test_timeline_blocks_and_audio_offsets")
