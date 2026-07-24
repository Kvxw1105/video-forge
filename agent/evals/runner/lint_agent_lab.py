"""Static checks for the Phase 0 Video Agent Lab assets."""

from __future__ import annotations

import json
import re
from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parents[2]
TOOL_RE = re.compile(r"^\s*tool:\s*([a-zA-Z0-9_]+)\s*$")
ID_RE = re.compile(r"^id:\s*([a-zA-Z0-9_-]+)\s*$", re.MULTILINE)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    manifest = json.loads((AGENT_ROOT / "manifest.json").read_text(encoding="utf-8"))
    errors: list[str] = []

    for group in ("contracts", "prompts", "recipes", "policies"):
        for rel in manifest[group]:
            if not (AGENT_ROOT / rel).exists():
                errors.append(f"missing {group[:-1]}: {rel}")

    known_tools = set(manifest["tools"])
    recipe_ids: set[str] = set()
    for rel in manifest["recipes"]:
        path = AGENT_ROOT / rel
        text = _read(path)
        match = ID_RE.search(text)
        if not match:
            errors.append(f"{rel}: missing id")
        else:
            recipe_ids.add(match.group(1))
        for tool in TOOL_RE.findall(text):
            if tool not in known_tools:
                errors.append(f"{rel}: unknown tool {tool}")
        if "no_free_start_end" not in text and "timing_authority" not in text:
            errors.append(f"{rel}: missing timing constraint")
        if "no_cross_block_scenes" not in text and "scene_boundary: block" not in text:
            errors.append(f"{rel}: missing block boundary constraint")

    if recipe_ids != {"structured-knowledge-video", "existing-assets-recut", "book-summary-short"}:
        errors.append(f"unexpected recipe ids: {sorted(recipe_ids)}")

    policy_text = "\n".join(_read(AGENT_ROOT / rel) for rel in manifest["policies"])
    for required in ("paid_tts", "paid_llm", "mutate_subtitle_timing", "overwrite_editable_draft"):
        if required not in policy_text:
            errors.append(f"policy missing required operation: {required}")

    result = {
        "status": "failed" if errors else "passed",
        "recipeIds": sorted(recipe_ids),
        "toolCount": len(known_tools),
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
