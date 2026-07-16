"""Regression checks for audio cue generation.
Run: python scripts/test_audio_cues.py
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from engines.audio_analyzer import generate_cue_points


def test_energy_mode_returns_one_cue_per_requested_image():
    analysis = {
        "duration": 10.0,
        "beats": [],
        "onsets": [],
        "energy": [
            {"time": 0.0, "value": 0.1},
            {"time": 2.0, "value": 0.9},
            {"time": 4.0, "value": 0.9},
            {"time": 6.0, "value": 0.9},
            {"time": 8.0, "value": 0.1},
        ],
        "sections": [],
    }
    cues = generate_cue_points(analysis, 8, "energy")
    assert len(cues) == 8, cues
    assert cues[0]["time"] >= 0
    assert cues[-1]["time"] < analysis["duration"]


def test_section_mode_returns_one_cue_per_requested_image():
    analysis = {
        "duration": 12.0,
        "beats": [],
        "onsets": [],
        "energy": [],
        "sections": [
            {"start": 0.0, "end": 3.0, "type": "low", "avg_energy": 0.1},
            {"start": 3.0, "end": 12.0, "type": "high", "avg_energy": 0.8},
        ],
    }
    cues = generate_cue_points(analysis, 10, "section")
    assert len(cues) == 10, cues
    assert cues == sorted(cues, key=lambda x: x["time"])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
