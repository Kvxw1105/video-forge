"""Pure compilation of structured Episode variants into a legacy project view."""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from models.project import Project


@dataclass(frozen=True)
class CompiledStructuredBlock:
    id: str
    type: str
    text: str
    revision: int


@dataclass(frozen=True)
class CompiledStructuredVariant:
    episode_id: str
    variant_id: str
    variant_name: str
    blocks: tuple[CompiledStructuredBlock, ...]
    block_ids: tuple[str, ...]
    script: str
    warnings: tuple[str, ...]
    project_view: dict[str, Any]


def compile_structured_variant(project: Project | dict, variant_id: str) -> CompiledStructuredVariant:
    """Compile explicit block references without mutating or persisting ``project``."""
    raw = project.model_dump(mode="python") if isinstance(project, Project) else deepcopy(project)
    structured = raw.get("structuredContent")
    if not isinstance(structured, dict):
        raise ValueError("project is not a structured project")
    episode = structured.get("episode")
    if not isinstance(episode, dict):
        raise ValueError("structuredContent.episode is invalid")
    variants = episode.get("variants") or []
    variant = next((item for item in variants if item.get("id") == variant_id), None)
    if variant is None:
        raise KeyError(variant_id)
    blocks_by_id = {item.get("id"): item for item in episode.get("blocks") or []}
    warnings: list[str] = []
    compiled: list[CompiledStructuredBlock] = []
    for block_id in variant.get("blockIds") or []:
        block = blocks_by_id[block_id]
        if not block.get("enabled", True):
            warnings.append(f"block {block_id} is disabled and was skipped")
            continue
        text = str(block.get("text") or "").strip()
        if not text:
            warnings.append(f"block {block_id} has empty text and was skipped")
            continue
        compiled.append(CompiledStructuredBlock(
            id=block_id,
            type=str(block.get("type")),
            text=text,
            revision=int(block.get("revision", 1)),
        ))
    script = "\n\n".join(block.text for block in compiled)
    project_view = deepcopy(raw)
    project_view["script"] = script
    structured_view = project_view.get("structuredContent")
    if isinstance(structured_view, dict) and isinstance(structured_view.get("episode"), dict):
        structured_view["episode"]["activeVariantId"] = variant_id
    return CompiledStructuredVariant(
        episode_id=str(episode.get("episodeId")),
        variant_id=str(variant.get("id")),
        variant_name=str(variant.get("name") or ""),
        blocks=tuple(compiled),
        block_ids=tuple(block.id for block in compiled),
        script=script,
        warnings=tuple(warnings),
        project_view=project_view,
    )
