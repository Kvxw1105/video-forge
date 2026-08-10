import base64
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_generate_voiceover_edge_passes_rate_and_pitch(monkeypatch, tmp_path):
    captured = {}

    class FakeCommunicate:
        def __init__(self, text, voice, *, rate="+0%", volume="+0%", pitch="+0Hz"):
            captured["text"] = text
            captured["voice"] = voice
            captured["rate"] = rate
            captured["volume"] = volume
            captured["pitch"] = pitch

        async def save(self, output_path):
            Path(output_path).write_bytes(b"mp3")

    fake_edge_tts = types.ModuleType("edge_tts")
    fake_edge_tts.Communicate = FakeCommunicate
    monkeypatch.setitem(sys.modules, "edge_tts", fake_edge_tts)

    from engines import voiceover

    importlib.reload(voiceover)

    out_dir = tmp_path / "voice"
    out_dir.mkdir()

    result_path, duration = voiceover.generate_voiceover(
        "你好",
        out_dir,
        engine="edge",
        speed=25,
        pitch=6,
        settings=types.SimpleNamespace(edgeVoice="zh-CN-XiaoxiaoNeural"),
    )

    assert captured["rate"] == "+25%"
    assert captured["pitch"] == "+6Hz"
    assert result_path.exists()
    assert duration >= 0


def test_synthesize_fish_includes_speed(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

        def __init__(self):
            self.headers = {"content-type": "audio/mpeg"}
            self.content = b"mp3"

        def raise_for_status(self):
            return None

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr("engines.voiceover.httpx.post", fake_post)

    from engines import voiceover

    data = voiceover.synthesize_fish(
        "你好",
        api_key="fish-key",
        reference_id="voice-id",
        model="s2.1-pro-free",
        fmt="mp3",
        speed=1.4,
    )

    assert data == b"mp3"
    assert captured["json"]["prosody"]["speed"] == 1.4
    assert captured["json"]["reference_id"] == "voice-id"


def test_synthesize_volcengine_decodes_streamed_audio(monkeypatch):
    from engines import voiceover

    captured = {}

    class FakeResponse:
        headers = {"content-type": "application/json"}
        status_code = 200

        def raise_for_status(self):
            return None

        def iter_text(self):
            yield json.dumps({"code": 0, "data": base64.b64encode(b"first").decode()})
            yield "\n" + json.dumps({"code": 0, "data": base64.b64encode(b"second").decode()})

    class FakeStream:
        def __enter__(self):
            return FakeResponse()

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_stream(method, url, *, headers=None, json=None, timeout=None):
        captured.update(method=method, url=url, headers=headers, json=json, timeout=timeout)
        return FakeStream()

    monkeypatch.setattr(voiceover.httpx, "stream", fake_stream)

    data = voiceover.synthesize_volcengine("你好", api_key="volc-key", speaker_id="S_kv", speech_rate=25)

    assert data == b"firstsecond"
    assert captured["method"] == "POST"
    assert captured["url"] == voiceover.VOLC_TTS_URL
    assert captured["headers"]["X-Api-Key"] == "volc-key"
    assert captured["headers"]["X-Api-Resource-Id"] == "seed-icl-2.0"
    assert captured["json"]["req_params"]["speaker"] == "S_kv"
    assert captured["json"]["req_params"]["audio_params"]["speech_rate"] == 25


def test_synthesize_volcengine_accepts_volcengine_success_code(monkeypatch):
    from engines import voiceover

    class FakeResponse:
        headers = {"content-type": "application/json"}
        status_code = 200

        def raise_for_status(self):
            return None

        def iter_text(self):
            yield json.dumps({"code": 20000000, "data": base64.b64encode(b"audio").decode()})

    class FakeStream:
        def __enter__(self):
            return FakeResponse()

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(voiceover.httpx, "stream", lambda *args, **kwargs: FakeStream())

    assert voiceover.synthesize_volcengine("你好", api_key="volc-key", speaker_id="S_kv") == b"audio"


def test_synthesize_volcengine_explains_legacy_credential_401(monkeypatch):
    from engines import voiceover

    class FakeResponse:
        headers = {"content-type": "application/json"}
        status_code = 401

        def raise_for_status(self):
            raise AssertionError("401 should be explained before raise_for_status")

    class FakeStream:
        def __enter__(self):
            return FakeResponse()

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(voiceover.httpx, "stream", lambda *args, **kwargs: FakeStream())

    with pytest.raises(RuntimeError, match="API Key.*Access Token.*Secret Key"):
        voiceover.synthesize_volcengine("你好", api_key="legacy-token", speaker_id="S_kv")


def test_generate_voiceover_custom_uses_requested_speed(monkeypatch, tmp_path):
    from engines import voiceover

    captured = {}

    def fake_custom(text, api_url, api_key="", speed=0):
        captured["speed"] = speed
        return b"mp3"

    monkeypatch.setattr(voiceover, "synthesize_custom", fake_custom)
    def fake_concat(part_paths, output_dir):
        final_path = output_dir / "voiceover_test.mp3"
        final_path.write_bytes(b"mp3")
        return final_path

    monkeypatch.setattr(voiceover, "_concat_with_gaps", fake_concat)
    monkeypatch.setattr(voiceover, "probe_duration", lambda path: 1.0)

    result_path, duration = voiceover.generate_voiceover(
        "你好",
        tmp_path,
        engine="custom",
        speed=1.5,
        settings=types.SimpleNamespace(customApiUrl="https://example.test/tts", customApiKey="", customSpeed=0.4),
    )

    assert captured["speed"] == 1.5
    assert result_path.exists()
    assert duration == 1.0


def test_voiceover_volume_is_serialized_for_jianying(monkeypatch, tmp_path):
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
            self.material_instance = {"path": path, "kwargs": dict(kwargs)}
            self.fade = None
            self.clip_settings = FakeClipSettings()

        def add_fade(self, *args, **kwargs):
            self.fade = (args, kwargs)

    class FakeTrack:
        def __init__(self, name):
            self.name = name
            self.segments = []

        def add_segment(self, segment):
            self.segments.append(segment)

    class FakeScript:
        def __init__(self):
            self.tracks = {}
            self.materials = types.SimpleNamespace(audio_fades=[])

        def add_track(self, track_type, name):
            self.tracks[name] = FakeTrack(name)

        def add_material(self, material):
            return material

        def import_srt(self, *args, **kwargs):
            return None

        def save(self):
            return None

    created_scripts = []

    class FakeDraftFolder:
        def __init__(self, base_dir):
            self.base_dir = base_dir

        def create_draft(self, *args, **kwargs):
            (Path(self.base_dir) / args[0]).mkdir()
            script = FakeScript()
            created_scripts.append(script)
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
    monkeypatch.setattr(jianying, "_resolve_path", lambda file_path: Path(file_path) if file_path else None)
    monkeypatch.setattr(jianying, "probe_media_duration", lambda path: 2.0)
    monkeypatch.setattr(jianying, "_audio_fade_seconds", lambda track, play_dur: (0.0, 0.0))

    asset_path = tmp_path / "asset.png"
    asset_path.write_bytes(b"asset")
    voiceover_path = tmp_path / "voiceover.mp3"
    voiceover_path.write_bytes(b"mp3")

    project = {
        "id": "proj_test",
        "name": "Test Project",
        "canvas": {"width": 1080, "height": 1920, "fps": 30},
        "segments": [
            {
                "id": "seg_1",
                "assetPath": str(asset_path),
                "type": "image",
                "start": 0,
                "end": 1,
                "transform": {"x": 0.5, "y": 0.5, "scale": 0.85, "rotation": 0},
            }
        ],
        "audio": {
            "voiceovers": [
                {
                    "id": "vo_1",
                    "file": str(voiceover_path),
                    "volume": 0.25,
                    "isActive": True,
                }
            ],
            "bgm": {"tracks": []},
            "sfx": [],
        },
        "subtitles": [],
        "overlays": {},
        "exportSettings": {"outputDir": str(tmp_path / "drafts")},
        "timeline": {"voiceoverStartAt": 0},
    }

    draft_dir = jianying.generate_jianying_draft(project, output_dir=tmp_path / "drafts")

    assert draft_dir.exists()
    voiceover_segment = created_scripts[0].tracks["voiceover"].segments[0]
    assert voiceover_segment.kwargs["volume"] == 0.25
