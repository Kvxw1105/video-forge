from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


StepKind = Literal["tool", "approval", "wait", "inspection", "evaluation"]
RunStatus = Literal[
    "draft",
    "running",
    "waiting",
    "waiting_assets",
    "waiting_approval",
    "failed",
    "recoverable",
    "succeeded",
    "cancelled",
]


@dataclass(frozen=True)
class RecipeStep:
    id: str
    kind: StepKind
    completionCondition: str
    required: bool = True
    tool: str | None = None
    policy: str | None = None
    inputFrom: list[str] = field(default_factory=list)
    produces: list[str] = field(default_factory=list)
    retry: str | None = None
    onError: str = "fail"
    auto: bool = True
    condition: str | None = None


@dataclass(frozen=True)
class Recipe:
    id: str
    version: int
    description: str
    inputContract: dict[str, Any]
    steps: list[RecipeStep]


@dataclass(frozen=True)
class PolicyDecision:
    decision: Literal["allow", "approval_required", "deny"]
    policyId: str
    risk: Literal["low", "medium", "high"]
    reason: str
    invalidatedArtifacts: list[str] = field(default_factory=list)
    estimatedCost: dict[str, Any] | None = None
