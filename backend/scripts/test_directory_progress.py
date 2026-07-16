import copy
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engines.renderer import render_preview


def test_directory_progress_render_smoke():
    project = {
        "canvas": {"width": 320, "height": 240, "fps": 25, "background": {"type": "color", "value": "#000000"}},
        "segments": [],
        "subtitles": [],
        "timeline": {"voiceoverStartAt": 0.5},
        "audio": {"voiceovers": [{"id": "vo", "file": "", "duration": 2.0, "isActive": True}]},
        "overlays": {
            "subtitle_enabled": True,
            "directoryProgress": {
                "enabled": True,
                "mode": "marquee_text",
                "text": "起势｜转折｜高潮｜余韵",
                "fontSize": 18,
                "color": "#F4EBDD",
                "opacity": 0.8,
                "y": 0.92,
                "startX": -0.3,
                "endX": 1.0,
            },
        },
    }
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "dir_progress.mp4"
        render_preview(copy.deepcopy(project), out)
        assert out.exists() and out.stat().st_size > 0


if __name__ == "__main__":
    test_directory_progress_render_smoke()
    print("PASS directory progress render smoke")
