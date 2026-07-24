"""Smoke test for BGM trim in renderer and jianying adapter."""
import json
import shutil
import tempfile
from pathlib import Path

# Add backend to path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from process_utils import run as run_process
from engines.renderer import _prepare_multi_bgm, _premix_audio
from shared.media_probe import probe_media_duration
from adapters.jianying import generate_jianying_draft


def _run(cmd, timeout=30):
    return run_process(cmd, timeout=timeout)


def make_video(path: Path, duration: float):
    """Generate a blank video mp4 of given duration."""
    _run([
        "ffmpeg", "-y", "-f", "lavfi", "-i",
        f"color=c=black:s=320x240:d={duration}",
        "-t", str(duration), "-pix_fmt", "yuv420p", str(path)
    ], timeout=30)


def make_bgm(path: Path, duration: float):
    """Generate a silent-ish sine wave mp3 of given duration."""
    _run([
        "ffmpeg", "-y", "-f", "lavfi", "-i",
        f"sine=frequency=1000:duration={duration}",
        "-t", str(duration), str(path)
    ], timeout=30)


def test_multi_bgm_trim():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        bgm = td / "bgm.mp3"
        make_bgm(bgm, 60.0)

        tracks = [{
            "file": str(bgm),
            "volume": 0.5,
            "trimStart": 10.0,
            "trimEnd": 30.0,
            "fadeIn": 0.0,
            "fadeOut": 0.0,
        }]
        prepared = _prepare_multi_bgm(tracks, td)
        dur = probe_media_duration(prepared)
        print(f"multi_bgm_trim: prepared={prepared}, duration={dur:.2f}")
        assert abs(dur - 20.0) < 0.5, f"Expected 20s, got {dur}s"
        print("PASS test_multi_bgm_trim")


def test_jianying_bgm_trim():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        bgm = td / "bgm.mp3"
        make_bgm(bgm, 60.0)
        vid = td / "video.mp4"
        make_video(vid, 8.0)

        project = {
            "id": "test_trim",
            "name": "Test Trim",
            "canvas": {"width": 1080, "height": 1920, "ratio": "9:16", "fps": 30},
            "audio": {
                "voiceover": {"file": "", "volume": 1.0},
                "bgm": {
                    "tracks": [{
                        "file": str(bgm),
                        "volume": 0.5,
                        "trimStart": 10.0,
                        "trimEnd": 30.0,
                        "fadeIn": 0.0,
                        "fadeOut": 0.0,
                    }]
                }
            },
            "segments": [{
                "assetPath": str(vid),  # blank video placeholder
                "type": "video",
                "start": 0,
                "end": 8,
                "transform": {"x": 0.5, "y": 0.5, "scale": 0.85, "rotation": 0, "fit": "contain"}
            }],
            "subtitles": [],
            "overlays": {"subtitle_enabled": False},
            "assets": [],
            "exportSettings": {"outputDir": str(td / "export")},
        }
        draft_dir = generate_jianying_draft(project, output_dir=td / "drafts").final_path
        draft_content_path = draft_dir / "draft_content.json"
        assert draft_content_path.exists(), "draft_content.json not generated"
        data = json.loads(draft_content_path.read_text(encoding="utf-8"))

        # Find BGM audio segment duration
        materials = data.get("materials", {})
        audios = materials.get("audios", [])
        print(f"jianying audios count: {len(audios)}")
        for a in audios:
            print(f"  audio: path={a.get('path', '')}, duration={a.get('duration', 0)}")

        # Check tracks
        tracks = data.get("tracks", [])
        for t in tracks:
            if t.get("type") == 0:  # audio track
                for seg in t.get("segments", []):
                    print(f"  audio segment: target_timerange={seg.get('target_timerange')}, source_timerange={seg.get('source_timerange')}")
        print("PASS test_jianying_bgm_trim (draft generated)")


if __name__ == "__main__":
    test_multi_bgm_trim()
    test_jianying_bgm_trim()
