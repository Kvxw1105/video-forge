import base64
import io
import json
import math
import struct
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.fish_timestamp_tts import FishTimestampError, parse_fish_timestamp_sse


def wav_bytes(seconds=1):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(8000)
        out.writeframes(b"".join(struct.pack("<h", int(5000 * math.sin(2 * math.pi * 220 * i / 8000))) for i in range(int(seconds * 8000))))
    return buf.getvalue()


def event(payload):
    return ("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode()


def test_parser_preserves_audio_arrival_order_and_latest_alignment_snapshot():
    audio = wav_bytes()
    stream = b"".join([
        event({"chunk_seq": 1, "chunk_audio_duration": 0.5, "audio_base64": base64.b64encode(audio[:100]).decode(), "alignment": {"segments": [{"text": "世界", "start": 0, "end": 0.4}]}}),
        event({"chunk_seq": 1, "alignment": {"segments": [{"text": "世界", "start": 0.1, "end": 0.45}]}}),
        b": comment\n",
        event({"chunk_seq": 2, "chunk_audio_duration": 0.5, "audio_base64": base64.b64encode(audio[100:]).decode(), "alignment": None}),
    ])
    parsed = parse_fish_timestamp_sse(stream)
    assert parsed.audio_bytes == audio
    assert parsed.alignment_by_chunk[1]["segments"][0]["start"] == 0.1
    assert parsed.segments[0].start == 0.1
    assert parsed.segments[0].end == 0.45
    assert parsed.duration >= 0.5


def test_parser_supports_multiline_data_and_invalid_json():
    parsed = parse_fish_timestamp_sse(b'data: {"chunk_seq": 0,\n' b'data: "audio_duration": 1}\n\n')
    assert parsed.duration == 1
    with pytest.raises(FishTimestampError):
        parse_fish_timestamp_sse(b"data: {bad}\n\n")
