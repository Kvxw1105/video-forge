"""Build bounded, product-authoritative Director context from SRT and projects."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import re
from typing import Any, Mapping

from .capability_registry import CapabilityRegistry

_SRT_BLOCK = re.compile(
    r"(?:^|\n)\s*(?P<index>\d+)\s*\n"
    r"(?P<start>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*"
    r"(?P<end>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*\n"
    r"(?P<text>.*?)(?=\n\s*\n|\Z)",
    re.DOTALL,
)


def _seconds(value: str) -> float:
    hours, minutes, seconds = value.replace(",", ".").split(":")
    return round(int(hours) * 3600 + int(minutes) * 60 + float(seconds), 3)


def parse_srt(srt_text: str) -> list[dict[str, Any]]:
    """Parse the SRT subset VideoForge accepts and reject invalid timing early."""
    subtitles: list[dict[str, Any]] = []
    previous_end = -1.0
    for match in _SRT_BLOCK.finditer(srt_text.replace("\r\n", "\n").strip()):
        start, end = _seconds(match["start"]), _seconds(match["end"])
        text = " ".join(line.strip() for line in match["text"].splitlines() if line.strip())
        if not text or end <= start:
            raise ValueError(f"invalid SRT cue {match['index']}")
        if start < previous_end:
            raise ValueError(f"overlapping SRT cue {match['index']}")
        subtitles.append({"id": f"srt_{match['index']}", "start": start, "end": end, "text": text})
        previous_end = end
    if not subtitles and srt_text.strip():
        raise ValueError("no valid SRT cues found")
    return subtitles


class ProductContextBuilder:
    """Produce a bounded JSON-ready context. It never mutates the supplied project."""

    schema_version = "videoforge-product-context/v1"

    def __init__(self, registry: CapabilityRegistry | None = None, *, max_subtitles: int = 120, max_text_chars: int = 240):
        self.registry = registry or CapabilityRegistry()
        self.max_subtitles = max_subtitles
        self.max_text_chars = max_text_chars

    def build(
        self,
        *,
        recipe_id: str,
        project: Mapping[str, Any] | None = None,
        srt_text: str | None = None,
        factory_context: Mapping[str, Any] | None = None,
        pending_approvals: list[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if project is not None and srt_text is not None:
            raise ValueError("provide project or srt_text, not both")
        raw_project = deepcopy(dict(project or {}))
        subtitles = list(raw_project.get("subtitles") or [])
        source = "project" if project is not None else "srt"
        if srt_text is not None:
            subtitles = parse_srt(srt_text)
            raw_project = {"id": "", "name": "Imported SRT", "script": " ".join(item["text"] for item in subtitles)}
        binding = self.registry.bind_recipe(recipe_id)
        result = {
            "schemaVersion": self.schema_version,
            "source": source,
            "inputKeys": ["srt_text"] if srt_text is not None else (["project_id"] if raw_project.get("id") else []),
            "project": self._project_summary(raw_project),
            "subtitleTimeline": self._subtitle_summary(subtitles),
            "structuredEpisode": self._structured_summary(raw_project.get("structuredContent") or {}),
            "assetCoverage": self._asset_coverage(raw_project),
            "factory": self._factory_summary(factory_context or {}),
            "pendingApprovals": self._approval_summary(pending_approvals or []),
            "recipe": {
                "id": binding.recipe_id,
                "version": binding.recipe_version,
                "requiredInputs": list(binding.required_inputs),
                "optionalInputs": list(binding.optional_inputs),
                "steps": list(binding.steps),
            },
            "availableTools": list(binding.capabilities),
        }
        result["recipeInputs"] = self.registry.available_inputs(binding, result)
        return result

    def _project_summary(self, project: Mapping[str, Any]) -> dict[str, Any]:
        script = str(project.get("script") or "")
        return {
            "id": str(project.get("id") or ""),
            "name": str(project.get("name") or ""),
            "templateId": str(project.get("templateId") or ""),
            "canvas": self._pick(project.get("canvas") or {}, "ratio", "width", "height"),
            "script": self._truncate(script),
            "scriptChars": len(script),
        }

    def _subtitle_summary(self, subtitles: list[Mapping[str, Any]]) -> dict[str, Any]:
        cues = []
        for cue in subtitles[: self.max_subtitles]:
            cues.append({
                "id": str(cue.get("id") or ""),
                "start": float(cue.get("start") or 0),
                "end": float(cue.get("end") or 0),
                "text": self._truncate(str(cue.get("text") or ""), 160),
            })
        duration = max((float(item.get("end") or 0) for item in subtitles), default=0.0)
        digest = hashlib.sha256(repr([(item.get("start"), item.get("end"), item.get("text")) for item in subtitles]).encode()).hexdigest()[:16]
        return {"count": len(subtitles), "duration": duration, "digest": digest, "cues": cues, "omittedCueCount": max(0, len(subtitles) - len(cues))}

    def _structured_summary(self, structured: Mapping[str, Any]) -> dict[str, Any] | None:
        episode = structured.get("episode") if isinstance(structured, Mapping) else None
        if not isinstance(episode, Mapping):
            return None
        visual_plan = episode.get("visualPlan") or {}
        scenes = visual_plan.get("scenes") if isinstance(visual_plan, Mapping) else []
        blocks = episode.get("blocks") or []
        return {
            "episodeId": str(episode.get("episodeId") or ""),
            "activeVariantId": str(episode.get("activeVariantId") or ""),
            "blockCount": len(blocks),
            "blocks": [self._pick(item, "id", "title", "summary") for item in blocks[:30] if isinstance(item, Mapping)],
            "visualPlan": {
                "planId": str(visual_plan.get("planId") or ""),
                "sceneCount": len(scenes or []),
                "scenes": [self._pick(item, "id", "blockId", "summary", "requestedMediaType", "primaryAssetId") for item in (scenes or [])[:30] if isinstance(item, Mapping)],
            } if isinstance(visual_plan, Mapping) else None,
        }

    @staticmethod
    def _asset_coverage(project: Mapping[str, Any]) -> dict[str, Any]:
        assets = project.get("assets") or []
        structured = project.get("structuredContent") or {}
        episode = structured.get("episode") if isinstance(structured, Mapping) else {}
        plan = episode.get("visualPlan") if isinstance(episode, Mapping) else {}
        scenes = plan.get("scenes") if isinstance(plan, Mapping) else []
        missing = [str(item.get("id") or "") for item in scenes or [] if isinstance(item, Mapping) and not item.get("visualAssetIds")]
        return {"totalAssets": len(assets), "sceneCount": len(scenes or []), "boundSceneCount": len(scenes or []) - len(missing), "missingSceneIds": missing, "complete": bool(scenes) and not missing}

    @staticmethod
    def _factory_summary(factory: Mapping[str, Any]) -> dict[str, Any]:
        return ProductContextBuilder._pick(factory, "batchId", "itemId", "status", "phase", "projectId", "errorCode", "error")

    @staticmethod
    def _approval_summary(approvals: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return [ProductContextBuilder._pick(item, "id", "action", "status", "reason", "createdAt") for item in approvals[:20]]

    @staticmethod
    def _pick(value: Mapping[str, Any], *keys: str) -> dict[str, Any]:
        return {key: value.get(key) for key in keys if value.get(key) is not None}

    def _truncate(self, value: str, limit: int | None = None) -> str:
        limit = limit or self.max_text_chars
        return value if len(value) <= limit else f"{value[:limit]}..."
