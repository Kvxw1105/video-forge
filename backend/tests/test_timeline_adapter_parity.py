import re
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters import jianying
from engines import renderer
from shared.timeline_compiler import compile_project_timeline


def _seconds(value) -> float:
    return float(str(value).removesuffix("s"))


def test_ffmpeg_and_jianying_consume_identical_compiled_timing(monkeypatch, tmp_path):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    voice = tmp_path / "voice.mp3"
    first.write_bytes(b"image")
    second.write_bytes(b"image")
    voice.write_bytes(b"audio")
    project = {
        "id": "parity",
        "name": "Parity",
        "canvas": {"width": 1080, "height": 1920, "fps": 30},
        "segments": [
            {"id": "first", "assetPath": str(first), "type": "image", "start": 0, "end": 1},
            {"id": "second", "assetPath": str(second), "type": "image", "start": 1, "end": 2},
        ],
        "assets": [],
        "audio": {
            "voiceovers": [{"id": "vo", "file": str(voice), "duration": 2, "isActive": True, "volume": 1}],
            "bgm": {"tracks": []}, "sfx": [],
        },
        "subtitles": [{"id": "sub", "text": "once", "start": 0, "end": 1, "style": {}}],
        "overlays": {"subtitle_enabled": True},
        "timeline": {"voiceoverStartAt": 0.5, "blocks": []},
    }
    cue_points = [{"time": 0, "duration": 1}, {"time": 3, "duration": 1}]

    renderer_compile_calls = 0
    jianying_compile_calls = 0

    def renderer_compile(*args, **kwargs):
        nonlocal renderer_compile_calls
        renderer_compile_calls += 1
        return compile_project_timeline(*args, **kwargs)

    def jianying_compile(*args, **kwargs):
        nonlocal jianying_compile_calls
        jianying_compile_calls += 1
        return compile_project_timeline(*args, **kwargs)

    final_commands = []

    def fake_run(cmd, **kwargs):
        final_commands.append(cmd)
        Path(cmd[-1]).write_bytes(b"video")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(renderer, "compile_project_timeline", renderer_compile)
    monkeypatch.setattr(renderer, "_get_duration", lambda _path: 2.0)
    monkeypatch.setattr(renderer, "_premix_audio", lambda *args, **kwargs: None)
    monkeypatch.setattr(renderer, "_run_cmd", fake_run)
    renderer.render_preview(project, tmp_path / "preview.mp4", cue_points)

    command = final_commands[-1]
    ffmpeg_durations = []
    for index, token in enumerate(command):
        if token != "-i":
            continue
        source = str(command[index + 1])
        if source.startswith("color="):
            ffmpeg_durations.append(float(re.search(r":d=([0-9.]+)", source).group(1)))
        else:
            ffmpeg_durations.append(float(command[index - 1]))
    ffmpeg_timing = []
    cursor = 0.0
    for duration in ffmpeg_durations:
        ffmpeg_timing.append((cursor, cursor + duration, duration))
        cursor += duration
    filter_complex = command[command.index("-filter_complex") + 1]

    class FakeTrackType:
        video = "video"
        audio = "audio"
        text = "text"

    class FakeClipSettings:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeSegment:
        def __init__(self, path, **kwargs):
            self.path = path
            self.kwargs = kwargs
            self.material_instance = {"path": path}
            self.clip_settings = kwargs.get("clip_settings") or FakeClipSettings()
            self.fade = None

        def add_fade(self, *args):
            self.fade = args

    video_ranges = []
    subtitle_ranges = []

    class FakeVideoSegment(FakeSegment):
        def __init__(self, path, **kwargs):
            super().__init__(path, **kwargs)
            video_ranges.append(kwargs["target_timerange"])

    class FakeTextSegment(FakeSegment):
        def __init__(self, text, **kwargs):
            super().__init__(text, **kwargs)
            subtitle_ranges.append(kwargs["timerange"])

    class FakeTrack:
        def add_segment(self, segment):
            return None

    class FakeScript:
        def __init__(self, draft_dir):
            self.draft_dir = draft_dir
            self.tracks = {}
            self.materials = SimpleNamespace(audio_fades=[])

        def add_track(self, track_type, name):
            self.tracks[name] = FakeTrack()

        def add_material(self, material):
            return None

        def save(self):
            (self.draft_dir / "draft_content.json").write_bytes(b"draft")

    class FakeDraftFolder:
        def __init__(self, base_dir):
            self.base_dir = Path(base_dir)

        def create_draft(self, draft_name, *args, **kwargs):
            draft_dir = self.base_dir / draft_name
            draft_dir.mkdir()
            return FakeScript(draft_dir)

    monkeypatch.setattr(jianying, "compile_project_timeline", jianying_compile)
    monkeypatch.setattr(jianying, "_get_audio_duration", lambda _path: 2.0)
    monkeypatch.setattr(jianying, "_preprocess_media_with_adjustments", lambda *args: {})
    monkeypatch.setattr(jianying, "DraftFolder", FakeDraftFolder)
    monkeypatch.setattr(jianying, "VideoSegment", FakeVideoSegment)
    monkeypatch.setattr(jianying, "AudioSegment", FakeSegment)
    monkeypatch.setattr(jianying, "TextSegment", FakeTextSegment)
    monkeypatch.setattr(jianying, "TrackType", FakeTrackType)
    monkeypatch.setattr(jianying, "ClipSettings", FakeClipSettings)
    monkeypatch.setattr(
        jianying, "trange", lambda start, duration: (_seconds(start), _seconds(duration))
    )

    jianying.generate_jianying_draft(
        project, output_dir=tmp_path / "drafts", cue_points=cue_points
    )
    jianying_timing = [(start, start + duration, duration) for start, duration in video_ranges]

    assert renderer_compile_calls == 1
    assert jianying_compile_calls == 1
    assert ffmpeg_timing == jianying_timing
    assert ffmpeg_timing[-1][1] == 5.5
    assert "between(t,0.5,1.5)" in filter_complex
    assert subtitle_ranges == [(0.5, 1.0)]
