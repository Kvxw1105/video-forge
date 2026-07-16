import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_decode_srt_accepts_utf8_bom_and_gb18030():
    from shared.srt import decode_srt

    text = "1\r\n00:00:00,000 --> 00:00:01,250\r\n你好\r\n"

    assert decode_srt(text.encode("utf-8-sig")) == text
    assert decode_srt(text.encode("gb18030")) == text


def test_parse_srt_accepts_optional_indexes_dot_milliseconds_and_multiline_text():
    from shared.srt import parse_srt

    content = (
        "00:00:00.000 --> 00:00:01.250\r\n"
        "第一行\r\n第二行\r\n\r\n"
        "8\r\n00:00:01,500 --> 00:00:03,000\r\n下一条\r\n"
    )

    subtitles, ignored = parse_srt(content)

    assert ignored == 0
    assert subtitles == [
        {"id": "sub_001", "text": "第一行\n第二行", "start": 0.0, "end": 1.25},
        {"id": "sub_002", "text": "下一条", "start": 1.5, "end": 3.0},
    ]


def test_parse_srt_ignores_malformed_blocks_and_invalid_time_ranges():
    from shared.srt import parse_srt

    content = (
        "1\n00:00:00,000 --> 00:00:01,000\n有效\n\n"
        "2\nnot a timecode\n无效\n\n"
        "3\n00:00:03,000 --> 00:00:02,000\n倒置\n"
    )

    subtitles, ignored = parse_srt(content)

    assert [item["text"] for item in subtitles] == ["有效"]
    assert ignored == 2


def test_parse_srt_rejects_files_without_valid_captions():
    from shared.srt import parse_srt

    with pytest.raises(ValueError, match="没有识别到有效字幕"):
        parse_srt("这不是 SRT")


def test_transcript_and_serialization_use_current_subtitle_data():
    from shared.srt import serialize_srt, subtitles_to_transcript

    subtitles = [
        {"id": "a", "text": "第一行\n第二行", "start": 0, "end": 1.2346},
        {"id": "b", "text": "下一条", "start": 61.5, "end": 63},
    ]

    assert subtitles_to_transcript(subtitles) == "第一行 第二行\n下一条"
    assert serialize_srt(subtitles) == (
        "1\r\n"
        "00:00:00,000 --> 00:00:01,235\r\n"
        "第一行\r\n第二行\r\n\r\n"
        "2\r\n"
        "00:01:01,500 --> 00:01:03,000\r\n"
        "下一条\r\n"
    )


def test_serialize_srt_keeps_indexes_sequential_when_empty_captions_are_skipped():
    from shared.srt import serialize_srt

    subtitles = [
        {"text": "", "start": 0, "end": 1},
        {"text": "保留", "start": 1, "end": 2},
    ]

    assert serialize_srt(subtitles).startswith("1\r\n00:00:01,000")
