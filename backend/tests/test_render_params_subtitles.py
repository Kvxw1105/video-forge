import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_jianying_subtitle_position_uses_edge_like_coordinates():
    from shared.render_params import subtitle_to_jianying_transform

    assert subtitle_to_jianying_transform("bottom_center") == (0.0, -0.78)
    assert subtitle_to_jianying_transform("top_left") == (-0.78, 0.78)
    assert subtitle_to_jianying_transform("middle_right") == (0.78, 0.0)


def test_jianying_font_size_uses_readable_scale():
    from shared.render_params import font_size_to_jianying

    assert font_size_to_jianying(48) == 8.0
    assert font_size_to_jianying(24) == 4.0


def test_drawtext_uses_detected_chinese_font(monkeypatch):
    from engines import renderer

    monkeypatch.setattr(renderer, "get_drawtext_fontfile", lambda: r"C:\Windows\Fonts\msyh.ttc")

    filters = renderer._build_drawtexts(
        [
            {
                "text": "中文字幕",
                "start": 0,
                "end": 1,
                "style": {"fontSize": 36, "position": "bottom_center"},
            }
        ],
        True,
        1920,
        1080,
    )

    assert "fontfile='C\\:/Windows/Fonts/msyh.ttc'" in filters
