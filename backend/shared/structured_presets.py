"""Stable Block identifiers and deterministic Variant presets."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from shared.structured_import import TYPE_SLUGS

PUBLISH_TYPES = {"HOOK", "CTA_TAG", "PROBLEM", "STORY", "MECHANISM", "JUDGMENT", "METHOD", "SHORT_OUTRO", "COMMENT_CTA"}
MASTER_TYPES = {"PROBLEM", "STORY", "MECHANISM", "JUDGMENT", "METHOD"}
CHAPTER_TYPES = {"BRIDGE_IN", "PROBLEM", "STORY", "MECHANISM", "JUDGMENT", "METHOD", "BRIDGE_OUT"}


def build_blocks(sections: list[Any]) -> list[dict]:
    counts = defaultdict(int)
    blocks: list[dict] = []
    for section in sections:
        if isinstance(section, dict):
            detected = section.get("detectedType") or section.get("detected_type")
            text = section.get("text", "")
        else:
            detected = getattr(section, "detected_type", None)
            text = getattr(section, "text", "")
        if not detected:
            continue
        counts[detected] += 1
        slug = TYPE_SLUGS[detected]
        blocks.append({
            "id": f"{slug}_{counts[detected]:02d}",
            "type": detected,
            "text": text,
            "enabled": True,
            "revision": 1,
            "metadata": {},
        })
    return blocks


def build_default_structured_variants(blocks: list[dict]) -> dict:
    def variant(identifier: str, name: str, allowed: set[str]) -> dict:
        return {"id": identifier, "name": name, "blockIds": [b["id"] for b in blocks if b.get("type") in allowed], "metadata": {}}
    variants = [variant("publish", "Publish", PUBLISH_TYPES), variant("master", "Master", MASTER_TYPES), variant("chapter", "Chapter", CHAPTER_TYPES)]
    warnings = []
    for item in variants:
        if not item["blockIds"]:
            warnings.append(f"empty_variant:{item['id']}")
    active = next((item["id"] for item in variants if item["blockIds"]), None)
    if active is None:
        warnings.append("no_active_variant")
    return {"variants": variants, "activeVariantId": active, "warnings": warnings}
