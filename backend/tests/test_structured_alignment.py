import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.structured_alignment import FishAlignmentSegment, align_episode_blocks, normalize_alignment_text, generate_subtitles_from_alignment


def test_alignment_handles_chinese_punctuation_and_block_boundaries():
    blocks = [{"id": "a", "text": "你好，世界！"}, {"id": "b", "text": "这是第二段。"}]
    segments = [FishAlignmentSegment("你好世界", 0.2, 1.0, 0), FishAlignmentSegment("这是第二段", 1.2, 2.0, 1)]
    result = align_episode_blocks(blocks, segments, 2.2)
    assert result.overall_confidence >= 0.9
    assert result.blocks[0].source_start == 0
    assert result.blocks[-1].source_end == 2.2
    assert result.blocks[0].source_end <= result.blocks[1].source_start


def test_low_confidence_does_not_create_fake_ranges():
    result = align_episode_blocks([{"id": "a", "text": "完全不同"}], [FishAlignmentSegment("x", 0, 1)], 1)
    assert result.overall_confidence < 0.75
    assert result.blocks[0].source_end == 0
    assert result.warnings


def test_subtitles_keep_absolute_source_times_and_metadata():
    subtitles = generate_subtitles_from_alignment([FishAlignmentSegment("一条", 0.1, 0.4, content="一条")], "gen", {"a": (0, 1)})
    assert subtitles[0]["start"] == 0.1
    assert subtitles[0]["metadata"]["blockId"] == "a"
    assert normalize_alignment_text("Ａ，Ｂ！") == "ab"
