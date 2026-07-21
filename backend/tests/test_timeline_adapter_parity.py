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
    bgm = tmp_path / "bgm.mp3"
    sfx = tmp_path / "sfx.wav"
    first.write_bytes(b"image")
    second.write_bytes(b"image")
    voice.write_bytes(b"audio")
    bgm.write_bytes(b"audio")
    sfx.write_bytes(b"audio")
    project = {
        "id": "parity",
        "name": "Parity",
        "canvas": {"width": 1080, "height": 1920, "fps": 30},
        "segments": [
            {"id": "first", "assetPath": str(first), "type": "image", "start": 0, "end": 1,
             "keyframes": [
                 {"property": "scale_x", "time": 0, "value": 1.0},
                 {"property": "scale_x", "time": 1, "value": 1.2},
             ]},
            {"id": "second", "assetPath": str(second), "type": "image", "start": 1, "end": 2},
        ],
        "assets": [],
        "audio": {
            "voiceovers": [{"id": "vo", "file": str(voice), "duration": 2, "isActive": True, "volume": 1}],
            "bgm": {"tracks": [{
                "file": str(bgm), "startAt": 1, "trimStart": 2, "trimEnd": 8, "volume": 0.4
            }]},
            "sfx": [{
                "file": str(sfx), "startAt": 2, "trimStart": 1, "trimEnd": 4, "volume": 0.7
            }],
        },
        "subtitles": [{"id": "sub", "text": "once", "start": 0, "end": 1, "style": {}}],
        "overlays": {
            "subtitle_enabled": True,
            "directoryProgress": {"enabled": True, "text": "progress", "fontSize": 22},
        },
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
    renderer_probe_calls = []
    renderer_bgm_tracks = []
    renderer_sfx_tracks = []
    renderer_mix = []
    durations = {str(voice): 2.0, str(bgm): 10.0, str(sfx): 5.0}

    def fake_run(cmd, **kwargs):
        final_commands.append(cmd)
        Path(cmd[-1]).write_bytes(b"video")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(renderer, "compile_project_timeline", renderer_compile)
    monkeypatch.setattr(
        renderer, "probe_media_duration",
        lambda path: renderer_probe_calls.append(str(path)) or durations[str(path)],
    )
    monkeypatch.setattr(
        renderer, "_prepare_bgm",
        lambda tracks, *args, **kwargs: renderer_bgm_tracks.extend(tracks) or None,
    )
    monkeypatch.setattr(
        renderer, "_prepare_multi_bgm",
        lambda tracks, *args, **kwargs: renderer_sfx_tracks.extend(tracks) or "",
    )
    monkeypatch.setattr(
        renderer, "_premix_audio",
        lambda *args, **kwargs: renderer_mix.append((args, kwargs)) or None,
    )
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

    audio_ranges = {}

    class FakeSegment:
        def __init__(self, path, **kwargs):
            self.path = path
            self.kwargs = kwargs
            self.material_instance = {"path": path}
            self.clip_settings = kwargs.get("clip_settings") or FakeClipSettings()
            self.fade = None
            if str(path) in {str(voice), str(bgm), str(sfx)}:
                audio_ranges[str(path)] = (
                    kwargs.get("target_timerange"), kwargs.get("source_timerange")
                )

        def add_fade(self, *args):
            self.fade = args

        def add_keyframe(self, *args):
            video_keyframe_calls.append((self.path, args))

    video_ranges = []
    video_keyframe_calls = []
    text_ranges = {}

    class FakeVideoSegment(FakeSegment):
        def __init__(self, path, **kwargs):
            super().__init__(path, **kwargs)
            video_ranges.append(kwargs["target_timerange"])

    class FakeTextSegment(FakeSegment):
        def __init__(self, text, **kwargs):
            super().__init__(text, **kwargs)
            text_ranges[text] = kwargs["timerange"]

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

        def add_segment(self, segment, track_name=None):
            self.tracks[track_name].add_segment(segment)
            return self

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
    jianying_probe_calls = []
    monkeypatch.setattr(
        jianying, "probe_media_duration",
        lambda path: jianying_probe_calls.append(str(path)) or durations[str(path)],
    )
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
    assert ffmpeg_timing[-1][1] == 5.0
    assert command[command.index("-t", command.index("-filter_complex")) + 1] == "5.5"
    assert "between(t,0.5,1.5)" in filter_complex
    assert text_ranges["once"] == (0.5, 1.0)
    assert text_ranges["progress"] == (0.5, 2.0)
    assert renderer_probe_calls == [str(voice), str(bgm), str(sfx)]
    assert jianying_probe_calls == [str(voice), str(bgm), str(sfx)]
    assert renderer_bgm_tracks[0]["startAt"] == 1
    assert renderer_bgm_tracks[0]["trimStart"] == 2
    assert renderer_bgm_tracks[0]["trimEnd"] == 6.5
    assert renderer_sfx_tracks[0]["startAt"] == 2
    assert renderer_sfx_tracks[0]["trimStart"] == 1
    assert renderer_sfx_tracks[0]["trimEnd"] == 4
    assert audio_ranges[str(voice)][0] == (0.5, 2.0)
    assert audio_ranges[str(bgm)] == ((1.0, 4.5), (2.0, 4.5))
    assert audio_ranges[str(sfx)] == ((2.0, 3.0), (1.0, 3.0))
    assert len(video_keyframe_calls) >= 2
    assert [(call[1][0].name, call[1][1], call[1][2]) for call in video_keyframe_calls[:2]] == [
        ("scale_x", "0s", 1.0), ("scale_x", "1s", 1.2)
    ]
    assert renderer_mix[0][0][4] == 5.5


def test_jianying_lowering_splits_long_image_without_changing_coverage(tmp_path):
    asset = tmp_path / "long.png"
    asset.write_bytes(b"image")
    project = {
        "canvas": {"width": 1080, "height": 1920, "fps": 30},
        "segments": [{
            "id": "long", "assetPath": str(asset), "type": "image", "start": 0, "end": 14
        }],
        "audio": {"voiceovers": [], "bgm": {"tracks": []}, "sfx": []},
        "subtitles": [], "overlays": {}, "timeline": {"blocks": []},
    }
    compiled = compile_project_timeline(project)

    lowered = jianying._lower_jianying_visual_segments(compiled.visual_segments())

    assert [(clip["start"], clip["end"]) for clip in compiled.visual_segments()] == [(0.0, 14.0)]
    assert [(clip["start"], clip["end"]) for clip in lowered] == [
        (0.0, 6.0), (6.0, 12.0), (12.0, 14.0)
    ]
