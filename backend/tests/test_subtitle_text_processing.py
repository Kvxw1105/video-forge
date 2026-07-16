import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_spaces_are_normalized_to_commas_for_tts_but_dunhao_is_preserved():
    from shared.text_processing import normalize_script_for_tts

    text = "这 里 有 空 格、顿号 和 逗号，继续"
    assert normalize_script_for_tts(text) == "这，里，有，空，格、顿号，和，逗号，继续"


def test_subtitle_segments_split_on_commas_and_spaces_not_dunhao():
    from shared.text_processing import split_script_for_subtitles

    text = "开头黑幕，接着画面、配音，然后继续"
    assert split_script_for_subtitles(text) == [
        "开头黑幕，",
        "接着画面、配音，",
        "然后继续",
    ]


def test_long_segment_has_length_fallback():
    from shared.text_processing import split_script_for_subtitles

    text = "这是一整段没有逗号也没有空格所以需要兜底切开否则字幕会爆满"
    segments = split_script_for_subtitles(text, max_chars=10)

    assert all(len(segment) <= 10 for segment in segments)
    assert "".join(segments) == text
