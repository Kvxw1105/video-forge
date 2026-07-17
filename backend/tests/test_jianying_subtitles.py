import importlib
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_jianying_subtitles_are_exported_as_positioned_text_segments(monkeypatch, tmp_path):
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
            self.clip_settings = kwargs.get("clip_settings") or FakeClipSettings()

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
    monkeypatch.setattr(jianying, "_expand_segments_to_duration", lambda segments, total_duration: segments)
    monkeypatch.setattr(jianying, "_apply_cue_points", lambda segments, cue_points: segments)
    monkeypatch.setattr(jianying, "_segment_chunks", lambda seg, limit: iter([(0.0, 2.0)]))

    asset_path = tmp_path / "asset.png"
    asset_path.write_bytes(b"asset")

    project = {
        "id": "proj_subtitles",
        "name": "Subtitles",
        "canvas": {"width": 1080, "height": 1920, "fps": 30},
        "segments": [{"id": "seg_1", "assetPath": str(asset_path), "type": "image", "start": 0, "end": 2}],
        "audio": {"voiceovers": [], "bgm": {"tracks": []}, "sfx": []},
        "subtitles": [
            {
                "id": "sub_1",
                "text": "底部字幕",
                "start": 0,
                "end": 1,
                "style": {"fontSize": 36, "position": "bottom_center"},
            },
            {
                "id": "sub_2",
                "text": "顶部字幕",
                "start": 1,
                "end": 2,
                "style": {"fontSize": 24, "position": "top_left"},
            },
        ],
        "overlays": {"subtitle_enabled": True},
        "exportSettings": {"outputDir": str(tmp_path / "drafts")},
        "timeline": {"voiceoverStartAt": 0},
    }

    jianying.generate_jianying_draft(project, output_dir=tmp_path / "drafts")

    subtitle_segments = scripts[0].tracks["subtitles"].segments
    assert [segment.path for segment in subtitle_segments] == ["底部字幕", "顶部字幕"]
    assert subtitle_segments[0].clip_settings.transform_y == 0.78
    assert subtitle_segments[1].clip_settings.transform_x == -0.78
    assert subtitle_segments[0].kwargs["style"].size == 12.0
    assert subtitle_segments[1].kwargs["style"].size == 8.0
