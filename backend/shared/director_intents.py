"""Single source of truth for Scene intents in Director Pack protocol v1."""
from __future__ import annotations

from typing import Literal

SceneIntent = Literal[
    "keyword",
    "mechanism",
    "process",
    "causal",
    "comparison",
    "data",
    "topology",
    "human_action",
    "relationship",
    "generic",
]

SCENE_INTENTS: tuple[str, ...] = (
    "keyword",
    "mechanism",
    "process",
    "causal",
    "comparison",
    "data",
    "topology",
    "human_action",
    "relationship",
    "generic",
)

_INTENT_SET = frozenset(SCENE_INTENTS)


def is_scene_intent(value: str) -> bool:
    return value in _INTENT_SET
