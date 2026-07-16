"""Smoke tests for timeline block builder.
Run from repo root: python scripts/test_timeline_builder.py
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from shared.timeline_blocks import build_segments_from_blocks  # noqa: E402


def test_black_then_video_then_images_rest():
    assets = [
        {"id": "v1", "type": "video", "path": "v1.mp4"},
        {"id": "i1", "type": "image", "path": "i1.jpg"},
        {"id": "i2", "type": "image", "path": "i2.jpg"},
    ]
    blocks = [
        {"type": "black", "duration": 1.5, "bgColor": "#000000"},
        {"type": "assets", "duration": 2.0, "source": "videos", "mode": "ordered", "perAssetDuration": 1.0},
        {"type": "assets", "duration": "rest", "source": "images", "mode": "ordered", "perAssetDuration": 2.0},
    ]

    segs = build_segments_from_blocks(assets, blocks, 6.0)

    assert segs[0]["type"] == "black"
    assert segs[0]["start"] == 0
    assert segs[0]["end"] == 1.5
    assert all(s["assetPath"] == "v1.mp4" for s in segs[1:3])
    assert segs[-1]["end"] == 6.0
    assert {s["type"] for s in segs[3:]} == {"image"}


if __name__ == "__main__":
    test_black_then_video_then_images_rest()
    print("PASS test_black_then_video_then_images_rest")
