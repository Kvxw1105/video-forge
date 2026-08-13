from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ArtifactRegistry:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "artifacts.json"
        self.artifacts: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            self.artifacts = json.loads(self.path.read_text(encoding="utf-8"))

    def add(self, kind: str, data: Any, source: str | None = None) -> str:
        raw = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        ref = f"artifact_{kind}_{digest}"
        self.artifacts[ref] = {"artifactId": ref, "kind": kind, "source": source, "data": data}
        self.path.write_text(json.dumps(self.artifacts, ensure_ascii=False, indent=2), encoding="utf-8")
        return ref
