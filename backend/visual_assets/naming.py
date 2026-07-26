from __future__ import annotations

import re


def slugify(value: str) -> str:
    text = value.strip().lower().replace("_", "-")
    text = re.sub(r"[^a-z0-9-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "item"


def asset_filename(order: int, segment_id: str, template_id: str, ext: str) -> str:
    suffix = ext.lstrip(".").lower()
    stem = f"{order:04d}_{slugify(segment_id)}_{slugify(template_id)}"
    max_stem = 160 - len(suffix) - 1
    return f"{stem[:max_stem].rstrip('-')}.{suffix}"
