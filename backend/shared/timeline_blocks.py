"""Pure timeline block builder used by tests and future API migrations.

This mirrors the frontend builder: voiceover time is the spine; blocks only decide
what visuals fill that spine. Keep it tiny and boring.
"""
from __future__ import annotations

from copy import deepcopy


def build_segments_from_blocks(
    assets: list[dict],
    blocks: list[dict],
    total_duration: float,
    *,
    default_per_asset_duration: float = 1.0,
    warnings: list[str] | None = None,
) -> list[dict]:
    if total_duration <= 0:
        return []
    out: list[dict] = []
    cursor = 0.0

    effective_blocks = blocks or [{"type": "assets", "duration": "rest", "source": "all", "mode": "random"}]
    for block_index, block in enumerate(effective_blocks):
        if cursor >= total_duration - 1e-6:
            break
        raw_dur = block.get("duration", "rest")
        block_dur = total_duration - cursor if raw_dur == "rest" else float(raw_dur or 0)
        block_dur = max(0.0, min(block_dur, total_duration - cursor))
        if block_dur <= 0:
            continue

        if block.get("type") == "black":
            out.append({
                "id": f"seg_black_{block_index}",
                "assetPath": "",
                "type": "black",
                "start": cursor,
                "end": cursor + block_dur,
                "transform": {"x": 0.5, "y": 0.5, "scale": 1, "rotation": 0, "fit": "stretch"},
                "bgColor": block.get("bgColor", "#000000"),
            })
            cursor += block_dur
            continue

        source = block.get("source", "all")
        pool = [a for a in assets if source == "all" or (source == "images" and a.get("type") == "image") or (source == "videos" and a.get("type") == "video")]
        if not pool:
            out.append({
                "id": f"seg_block_fallback_{block_index}",
                "assetPath": "",
                "type": "black",
                "start": cursor,
                "end": cursor + block_dur,
                "transform": {"x": 0.5, "y": 0.5, "scale": 1, "rotation": 0, "fit": "stretch"},
                "bgColor": block.get("bgColor", "#000000"),
            })
            if warnings is not None:
                warnings.append(f"Timeline block {block_index} has no matching visual assets; using black fallback")
            cursor += block_dur
            continue
        if block.get("mode", "random") == "ordered":
            ordered = pool
        else:
            # Deterministic pseudo-random for tests/backends. Frontend may use Math.random for UX.
            ordered = sorted(pool, key=lambda a: a.get("id") or a.get("path") or "")

        per = max(0.05, float(block.get("perAssetDuration", default_per_asset_duration) or default_per_asset_duration))
        block_end = cursor + block_dur
        idx = 0
        max_items = max(1, min(10000, int(block_dur / 0.05) + len(ordered) + 2))
        while cursor < block_end - 1e-6 and idx < max_items:
            asset = ordered[idx % len(ordered)]
            seg_dur = min(per, block_end - cursor)
            out.append({
                "id": f"seg_{block_index}_{idx}",
                "assetPath": asset.get("path", ""),
                "type": "video" if asset.get("type") == "video" else "image",
                "start": cursor,
                "end": cursor + seg_dur,
                "transform": deepcopy(asset.get("transform") or {"x": 0.5, "y": 0.5, "scale": 0.85, "rotation": 0, "fit": "contain"}),
            })
            cursor += seg_dur
            idx += 1

    return out
