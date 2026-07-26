"""Focused executable contract for Product Harness v1."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.harness import CapabilityRegistry, ProductContextBuilder, parse_srt


SRT = """1
00:00:00,000 --> 00:00:02,000
First point.

2
00:00:02,100 --> 00:00:05,000
Second point.
"""


def main() -> None:
    cues = parse_srt(SRT)
    assert len(cues) == 2 and cues[1]["start"] == 2.1
    registry = CapabilityRegistry(ROOT / "agent" / "recipes")
    binding = registry.bind_recipe("structured-knowledge-video")
    assert binding.recipe_version == 1
    assert any(item["name"] == "bind_scene_assets" for item in binding.capabilities)

    context = ProductContextBuilder(registry).build(recipe_id=binding.recipe_id, srt_text=SRT)
    assert context["source"] == "srt"
    assert context["subtitleTimeline"]["count"] == 2
    assert context["recipeInputs"]["missingRequired"] == []
    assert context["project"]["scriptChars"] > 0
    assert context["availableTools"]

    project = {
        "id": "project-1", "name": "Demo", "script": "A short script", "assets": [{"id": "asset-1"}],
        "subtitles": cues,
        "structuredContent": {"episode": {"episodeId": "ep-1", "blocks": [{"id": "block-1", "title": "Intro"}], "visualPlan": {"planId": "plan-1", "scenes": [{"id": "scene-1", "blockId": "block-1", "visualAssetIds": []}]}}},
    }
    recut = ProductContextBuilder(registry).build(recipe_id="existing-assets-recut", project=project, factory_context={"batchId": "batch-1", "itemId": "item-1", "status": "awaiting_visual_assets"})
    assert recut["assetCoverage"]["missingSceneIds"] == ["scene-1"]
    assert recut["factory"]["batchId"] == "batch-1"
    assert recut["recipeInputs"]["missingRequired"] == []
    try:
        parse_srt("1\n00:00:02,000 --> 00:00:01,000\nBad")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid timing must be rejected")
    print("Product Harness v1 verification passed")


if __name__ == "__main__":
    main()
