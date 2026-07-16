"""Offset behavior checks for voiceover/subtitles and BGM timeline placement.
Run from repo root: python scripts/test_audio_offsets.py
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from engines.renderer import _build_drawtexts  # noqa: E402
from adapters.jianying import _track_play_window  # noqa: E402


def test_subtitle_drawtext_is_shifted_by_voiceover_start():
    filters = _build_drawtexts([
        {"text": "hello", "start": 1.0, "end": 2.0, "style": {"fontSize": 36, "position": "bottom_center"}}
    ], True, 1920, 1080, 1.5)
    assert "between(t,2.5,3.5)" in filters


def test_bgm_timeline_start_is_separate_from_source_trim():
    target_start, source_start, play_dur = _track_play_window(
        {"startAt": 3.0, "trimStart": 30.0, "trimEnd": 50.0},
        total_duration=60.0,
        full_duration=100.0,
    )
    assert target_start == 3.0
    assert source_start == 30.0
    assert play_dur == 20.0


if __name__ == "__main__":
    test_subtitle_drawtext_is_shifted_by_voiceover_start()
    test_bgm_timeline_start_is_separate_from_source_trim()
    print("PASS test_audio_offsets")
