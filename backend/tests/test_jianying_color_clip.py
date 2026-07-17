import importlib
import sys
import types
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_black_segment_exports_as_real_jianying_video_clip(monkeypatch, tmp_path):
    fake_pyjianying = types.ModuleType("pyJianYingDraft")
    fake_keyframe = types.ModuleType("pyJianYingDraft.keyframe")
    fake_text_segment = types.ModuleType("pyJianYingDraft.text_segment")

    class FakeTrackType:
        video = "video"
        audio = "audio"
        text = "text"

    class FakeClipSettings:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeTextStyle:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeSegment:
        def __init__(self, path, **kwargs):
            self.path = path
            self.kwargs = dict(kwargs)
            self.material_instance = {"path": path}
            self.clip_settings = FakeClipSettings()

    class FakeTrack:
        def __init__(self):
            self.segments = []

        def add_segment(self, segment):
            self.segments.append(segment)

    class FakeScript:
        def __init__(self):
            self.tracks = {}
            self.materials = types.SimpleNamespace(audio_fades=[])

        def add_track(self, track_type, name):
            self.tracks[name] = FakeTrack()

        def add_material(self, material):
            return material

        def import_srt(self, *args, **kwargs):
            return None

        def save(self):
            return None

    scripts = []

    class FakeDraftFolder:
        def __init__(self, base_dir):
            self.base_dir = base_dir

        def create_draft(self, *args, **kwargs):
            (Path(self.base_dir) / args[0]).mkdir()
            script = FakeScript()
            scripts.append(script)
            return script

    fake_pyjianying.ScriptFile = object
    fake_pyjianying.VideoSegment = FakeSegment
    fake_pyjianying.AudioSegment = FakeSegment
    fake_pyjianying.TextSegment = FakeSegment
    fake_pyjianying.DraftFolder = FakeDraftFolder
    fake_pyjianying.TrackType = FakeTrackType
    fake_pyjianying.trange = lambda start, dur: (start, dur)
    fake_pyjianying.ClipSettings = FakeClipSettings
    fake_keyframe.KeyframeProperty = object
    fake_text_segment.TextStyle = FakeTextStyle

    monkeypatch.setitem(sys.modules, "pyJianYingDraft", fake_pyjianying)
    monkeypatch.setitem(sys.modules, "pyJianYingDraft.keyframe", fake_keyframe)
    monkeypatch.setitem(sys.modules, "pyJianYingDraft.text_segment", fake_text_segment)

    from adapters import jianying

    importlib.reload(jianying)
    monkeypatch.setattr(jianying, "_preprocess_media_with_adjustments", lambda segments, adjustments, draft_dir: {})

    project = {
        "id": "proj_black",
        "name": "Black Opener",
        "canvas": {"width": 1080, "height": 1920, "fps": 30},
        "segments": [
            {"id": "black_1", "type": "black", "bgColor": "#000000", "start": 0, "end": 3},
        ],
        "audio": {"voiceovers": [], "bgm": {"tracks": []}, "sfx": []},
        "subtitles": [],
        "overlays": {},
        "exportSettings": {"outputDir": str(tmp_path / "drafts")},
        "timeline": {"voiceoverStartAt": 0},
    }

    draft_dir = jianying.generate_jianying_draft(project, output_dir=tmp_path / "drafts")

    assert draft_dir.exists()
    segment = scripts[0].tracks["main"].segments[0]
    assert Path(segment.path).name == "_vf_color_1080x1920_000000.png"
    assert segment.kwargs["target_timerange"] == ("0.0s", "3.0s")
