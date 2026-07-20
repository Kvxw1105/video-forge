from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def list_jianying_drafts(root: str | Path | None) -> list[dict[str, str]]:
    if not root:
        return []
    path = Path(root)
    if not path.is_dir():
        return []
    results: list[dict[str, str]] = []
    for draft in sorted(path.iterdir(), key=lambda item: item.name, reverse=True):
        if not draft.is_dir() or draft.name.startswith(".videoforge-") or not (draft / "draft_content.json").is_file():
            continue
        name = draft.name
        meta = draft / "draft_meta_info.json"
        if meta.is_file():
            try:
                name = str(json.loads(meta.read_text(encoding="utf-8")).get("draft_name") or name)
            except (OSError, ValueError, TypeError):
                pass
        results.append({"name": name, "folder": draft.name})
    return results


def inspect_jianying_status(root: str | Path | None) -> dict[str, Any]:
    path = Path(root) if root else None
    exists = bool(path and path.is_dir())
    drafts = list_jianying_drafts(path) if exists else []
    return {
        "detected": exists,
        "path": str(path.resolve()) if exists else None,
        "drafts": drafts,
        "directoryExists": exists,
        "writable": bool(exists and os.access(path, os.W_OK)),
        "draftCount": len(drafts),
    }
