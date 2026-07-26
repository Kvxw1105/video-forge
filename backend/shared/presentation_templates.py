"""Built-in presentation defaults for top-level narrative blocks.

Selections are stored in ``StructuredBlock.metadata.presentation``. This keeps
templates advisory and avoids adding a parallel project or timeline model.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


PRESENTATION_TEMPLATES: tuple[dict[str, Any], ...] = (
    {"id": "hook_impact", "name": "Strong opening", "blockTypes": ("HOOK",), "providerPreferences": ("ai_image", "code_visual_svg", "stickman_svg"), "presentationMode": "main", "granularity": "coarse", "presentationStyle": "impact_opening", "description": "One or two high-contrast opening visuals."},
    {"id": "story_sequence", "name": "Narrative sequence", "blockTypes": ("STORY",), "providerPreferences": ("ai_image", "library_video", "stickman_svg"), "presentationMode": "main", "granularity": "standard", "presentationStyle": "narrative_sequence", "description": "Sequence visuals that follow story beats."},
    {"id": "mechanism_explainer", "name": "Mechanism explainer", "blockTypes": ("MECHANISM",), "providerPreferences": ("code_visual_svg", "stickman_svg", "ai_image"), "presentationMode": "overlay", "granularity": "fine", "presentationStyle": "diagram_first", "description": "Diagram-first explanation with optional picture-in-picture."},
    {"id": "method_steps", "name": "Method steps", "blockTypes": ("METHOD",), "providerPreferences": ("ai_image", "code_visual_svg", "stickman_svg"), "presentationMode": "main", "granularity": "standard", "presentationStyle": "stepwise_explainer", "description": "Clear step-by-step explanatory visuals."},
    {"id": "outro_resolve", "name": "Closing resolution", "blockTypes": ("SHORT_OUTRO",), "providerPreferences": ("ai_image", "library_video"), "presentationMode": "main", "granularity": "coarse", "presentationStyle": "closing_resolution", "description": "A restrained closing visual and call to action."},
    {"id": "narrative_support", "name": "Narrative support", "blockTypes": ("CTA_TAG", "PROBLEM", "JUDGMENT", "BRIDGE_IN", "BRIDGE_OUT", "COMMENT_CTA"), "providerPreferences": ("ai_image", "library_video", "stickman_svg"), "presentationMode": "main", "granularity": "standard", "presentationStyle": "supporting_narrative", "description": "A flexible default for supporting narrative blocks."},
)
GRANULARITY_OPTIONS = ("coarse", "standard", "fine", "custom")


def list_presentation_templates() -> list[dict[str, Any]]:
    """Return API-safe catalog entries without exposing mutable module state."""
    return [
        {
            **deepcopy(template),
            "blockTypes": list(template["blockTypes"]),
            "providerPreferences": list(template["providerPreferences"]),
            "granularityOptions": list(GRANULARITY_OPTIONS),
        }
        for template in PRESENTATION_TEMPLATES
    ]


def presentation_for_block(block_type: str, suggested_template_id: str | None = None) -> dict[str, Any]:
    """Accept a compatible agent suggestion or resolve the block-type default."""
    compatible = [template for template in PRESENTATION_TEMPLATES if block_type in template["blockTypes"]]
    selected = next((template for template in compatible if template["id"] == suggested_template_id), None)
    source = "agent" if selected else "default"
    if selected is None:
        selected = compatible[0] if compatible else PRESENTATION_TEMPLATES[-1]
    return {
        "templateId": selected["id"],
        "source": source,
        "providerPreferences": list(selected["providerPreferences"]),
        "presentationMode": selected["presentationMode"],
        "granularity": selected["granularity"],
        "presentationStyle": selected["presentationStyle"],
        "visualPolicy": {},
    }
