"""Provider-neutral normalization for Agent-authored structured episodes."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from models.project import StructuredContent
from shared.structured_import import MAX_SOURCE_CHARS, TYPE_SLUGS
from shared.structured_presets import build_blocks, build_default_structured_variants


class ScriptStructuringError(ValueError):
    pass


class ScriptStructuringProvider(Protocol):
    """Future LLM adapters implement this seam; no provider is bundled here."""

    name: str

    def structure(self, request: "ScriptStructuringRequest") -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class ScriptStructuringRequest:
    source_text: str
    title: str = ""
    topic: str = ""
    target_duration_seconds: int | None = None
    profile_snapshot: Mapping[str, Any] | None = None


def _require_source(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScriptStructuringError("sourceText must not be empty")
    if len(value) > MAX_SOURCE_CHARS:
        raise ScriptStructuringError(f"sourceText exceeds {MAX_SOURCE_CHARS} characters")
    return value.strip()


def _profile_block_types(profile_snapshot: Mapping[str, Any] | None) -> set[str] | None:
    """Read the stored profile snapshot, while preserving the original loose seam."""
    if not isinstance(profile_snapshot, Mapping):
        return None
    raw = profile_snapshot.get("allowedBlockTypes", profile_snapshot.get("blockTypes"))
    if raw is None:
        embedded_profile = profile_snapshot.get("profile")
        if isinstance(embedded_profile, Mapping):
            blocks = embedded_profile.get("blocks")
            if not isinstance(blocks, list):
                raise ScriptStructuringError("profileSnapshot.profile.blocks must be a list")
            raw = [block.get("type") if isinstance(block, Mapping) else None for block in blocks]
    if raw is None:
        return None
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        raise ScriptStructuringError("profileSnapshot block types must be a list of strings")
    unknown = set(raw).difference(TYPE_SLUGS)
    if unknown:
        raise ScriptStructuringError(f"profileSnapshot contains unknown block types: {', '.join(sorted(unknown))}")
    return set(raw)


def _proposal_sections(proposal: Mapping[str, Any], allowed_types: set[str] | None) -> list[dict[str, str]]:
    raw_sections = proposal.get("sections")
    if not isinstance(raw_sections, list) or not raw_sections:
        raise ScriptStructuringError("proposal.sections must be a non-empty list")
    sections: list[dict[str, str]] = []
    for index, raw in enumerate(raw_sections):
        if not isinstance(raw, Mapping):
            raise ScriptStructuringError(f"proposal.sections[{index}] must be an object")
        block_type = raw.get("type", raw.get("detectedType"))
        section_text = raw.get("text")
        if not isinstance(block_type, str) or block_type not in TYPE_SLUGS:
            raise ScriptStructuringError(f"proposal.sections[{index}].type must be a known structured block type")
        if allowed_types is not None and block_type not in allowed_types:
            raise ScriptStructuringError(f"proposal.sections[{index}].type is not allowed by profileSnapshot")
        if not isinstance(section_text, str) or not section_text.strip():
            raise ScriptStructuringError(f"proposal.sections[{index}].text must not be empty")
        sections.append({"detectedType": block_type, "text": section_text.strip()})
    return sections


class ScriptStructuringService:
    """Turns an Agent proposal into validated ``StructuredContent`` data."""

    def __init__(self, provider: ScriptStructuringProvider | None = None):
        self.provider = provider

    def normalize(self, request: ScriptStructuringRequest, proposal: Mapping[str, Any], *, provider_name: str = "external_agent") -> dict[str, Any]:
        source_text = _require_source(request.source_text)
        if not isinstance(proposal, Mapping):
            raise ScriptStructuringError("proposal must be an object")
        profile_snapshot = dict(request.profile_snapshot) if isinstance(request.profile_snapshot, Mapping) else None
        sections = _proposal_sections(proposal, _profile_block_types(profile_snapshot))
        blocks = build_blocks(sections)
        variants = build_default_structured_variants(blocks)
        if not variants["activeVariantId"]:
            raise ScriptStructuringError("proposal does not produce an active variant")
        source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        profile_id = str((profile_snapshot or {}).get("id") or (profile_snapshot or {}).get("profileId") or "")
        episode = {
            "episodeId": f"episode_{hashlib.sha256(f'{source_text}\n{profile_id}'.encode('utf-8')).hexdigest()[:16]}",
            "title": str(proposal.get("title") or request.title or "Structured Episode").strip(),
            "topic": str(proposal.get("topic") or request.topic or "").strip(),
            "symbol": str(proposal.get("symbol") or "").strip(),
            "blocks": blocks, "variants": variants["variants"], "bindings": [], "activeVariantId": variants["activeVariantId"],
            "metadata": {"scriptStructuring": {"schemaVersion": 1, "provider": provider_name, "sourceHash": source_hash, "profileSnapshot": profile_snapshot, "targetDurationSeconds": request.target_duration_seconds, "timeStatus": "awaiting_voice_alignment"}},
        }
        content = StructuredContent(schemaVersion=1, episode=episode)
        return {"schemaVersion": 1, "episode": content.episode.model_dump(mode="python"), "warnings": list(variants["warnings"])}

    def propose(self, request: ScriptStructuringRequest) -> dict[str, Any]:
        if self.provider is None:
            raise ScriptStructuringError("script_structuring_provider_not_configured")
        proposal = self.provider.structure(request)
        return self.normalize(request, proposal, provider_name=str(getattr(self.provider, "name", self.provider.__class__.__name__)))
