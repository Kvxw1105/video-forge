from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _normalize(value: Any) -> Any:
    if isinstance(value, float):
        rounded = float(format(value, ".6f"))
        return int(rounded) if rounded.is_integer() else rounded
    if isinstance(value, dict):
        return {str(key): _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(_normalize(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_payload(payload: Any) -> str:
    return sha256_bytes(canonical_json_bytes(payload))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_hash_payload(item, route, config, exports) -> dict[str, Any]:
    return {
        "segmentId": item.id,
        "order": item.order,
        "blockId": item.blockId,
        "subtitleIds": item.subtitleIds,
        "start": item.start,
        "end": item.end,
        "text": item.text,
        "semantic": item.semantic.model_dump(mode="python"),
        "templateId": route.templateId,
        "templateVersion": route.templateVersion,
        "parameters": route.parameters,
        "canvas": config.canvas.model_dump(mode="python"),
        "theme": config.theme.model_dump(mode="python"),
        "providerVersion": config.providerVersion,
        "rendererVersion": config.rendererVersion,
        "exports": exports.model_dump(mode="python"),
        "seed": config.seed,
    }
