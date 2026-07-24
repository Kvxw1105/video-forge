"""Phase 0 eval case linter.

This runner intentionally does not execute VideoForge. It validates that the
fixed eval set is present and structurally ready for later runtime comparison.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "cases"
REQUIRED = {
    "id",
    "category",
    "recipeId",
    "goal",
    "fixtures",
    "expected",
    "metrics",
}


def main() -> int:
    files = sorted(CASES.glob("*.json"))
    errors: list[str] = []
    categories: dict[str, int] = {}

    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{path.name}: invalid json: {exc}")
            continue

        missing = sorted(REQUIRED - data.keys())
        if missing:
            errors.append(f"{path.name}: missing {', '.join(missing)}")

        category = str(data.get("category", "unknown"))
        categories[category] = categories.get(category, 0) + 1

        expected = data.get("expected", {})
        if not isinstance(expected, dict):
            errors.append(f"{path.name}: expected must be an object")
        elif "finalState" not in expected:
            errors.append(f"{path.name}: expected.finalState missing")

        metrics = data.get("metrics", {})
        if not isinstance(metrics, dict):
            errors.append(f"{path.name}: metrics must be an object")

    if len(files) < 20:
        errors.append(f"expected at least 20 cases, found {len(files)}")

    result = {
        "caseCount": len(files),
        "categories": categories,
        "status": "failed" if errors else "passed",
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
