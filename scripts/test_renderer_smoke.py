"""Smoke test for FFmpeg preview rendering.
Run: python scripts/test_renderer_smoke.py
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from engines.renderer import render_preview, _prepare_multi_bgm


def _require_ffmpeg():
    if not shutil.which("ffmpeg"):
        raise SystemExit("SKIP ffmpeg not found")


def test_render_preview_single_image_no_audio():
    _require_ffmpeg()
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        img = td / "red.png"
        out = td / "preview.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x180:d=0.1", "-frames:v", "1", str(img)],
            check=True,
            capture_output=True,
        )
        project = {
            "canvas": {"width": 320, "height": 180, "fps": 30, "background": {"value": "#ffffff"}},
            "segments": [{"assetPath": str(img), "start": 0, "end": 1, "transform": {"scale": 1, "fit": "contain"}}],
            "subtitles": [],
            "audio": {},
            "overlays": {"subtitle_enabled": True},
        }
        render_preview(project, out)
        assert out.exists(), out
        assert out.stat().st_size > 1000, out.stat().st_size


def test_prepare_multi_bgm_trims_and_concats_tracks():
    _require_ffmpeg()
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        a = td / "a.mp3"
        b = td / "b.mp3"
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(a)], check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=2", str(b)], check=True, capture_output=True)
        out = Path(_prepare_multi_bgm([
            {"file": str(a), "volume": 0.5, "trimStart": 0.0, "trimEnd": 1.0, "fadeIn": 0.1, "fadeOut": 0.1},
            {"file": str(b), "volume": 0.5, "trimStart": 0.5, "trimEnd": 1.5, "fadeIn": 0.0, "fadeOut": 0.0},
        ], td))
        assert out.exists(), out
        assert out.stat().st_size > 1000, out.stat().st_size


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
