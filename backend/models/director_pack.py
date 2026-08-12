"""Strict data-only Pydantic models for Director Pack protocol v1.

The Manifest is the canonical truth at distribution time. It may only
reference registered Providers, Provider templates and advisory Skills.
No executable field, no runtime expression and no ownership of
Project/VisualPlan/Timeline state is allowed.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.director_intents import SCENE_INTENTS

PACK_ID = r"^[a-z0-9][a-z0-9_-]{0,63}/[a-z0-9][a-z0-9_-]{0,63}$"
SEMVER = r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$"


class PackIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=PACK_ID)
    version: str = Field(pattern=SEMVER)


class Publisher(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    name: str = Field(default="", max_length=120)


class Compatibility(BaseModel):
    model_config = ConfigDict(extra="forbid")
    directorProtocol: str = "1.x"


class ScenePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy: Literal["semantic"] = "semantic"
    visualDensity: Literal["light", "balanced", "dense"] = "balanced"
    segmentationProposal: Literal["unsupported", "supported"] = "unsupported"


class RoutingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default: list[str] = Field(min_length=1)
    intents: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("default", "intents")
    @classmethod
    def _non_empty_values(cls, value):
        if isinstance(value, list):
            if any(not isinstance(item, str) or not item for item in value):
                raise ValueError("routing values must contain non-empty provider ids")
        else:
            for provider_ids in value.values():
                if any(not isinstance(item, str) or not item for item in provider_ids):
                    raise ValueError("routing intent values must contain non-empty provider ids")
        return value

    @field_validator("intents")
    @classmethod
    def _known_intent_keys(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        for intent in value:
            if intent not in SCENE_INTENTS:
                raise ValueError(f"unknown scene intent: {intent!r}")
        return value


class StylePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    anchor: str = Field(default="", max_length=2000)
    avoid: list[str] = Field(default_factory=list, max_length=100)


class RhythmPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    visualDensity: Literal["light", "balanced", "dense"] = "balanced"
    motionPreference: Literal["static", "gentle", "dynamic"] = "static"


class ContinuityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["project", "scene"] = "project"
    anchor: str = Field(default="", max_length=2000)


class CandidatePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    count: Literal[1, 2, 4] = 1


class AutoApprovalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowTrustedLocal: bool = True
    allowExternal: bool = False
    reviewOnFallback: bool = True
    reviewOnWarnings: bool = True


class ReviewApprovalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requireCandidateSelection: bool = True


class ApprovalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    defaultMode: Literal["auto", "review"] = "auto"
    auto: AutoApprovalPolicy = Field(default_factory=AutoApprovalPolicy)
    review: ReviewApprovalPolicy = Field(default_factory=ReviewApprovalPolicy)


class DurationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image: Literal["hold_to_scene"] = "hold_to_scene"
    video: Literal["exact", "crop", "loop", "speed_adjust", "reject"] = "reject"


class TemplateReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=64)
    useFor: list[str] = Field(default_factory=list, max_length=64)

    @field_validator("useFor")
    @classmethod
    def _known_intent_keys(cls, value: list[str]) -> list[str]:
        for intent in value:
            if intent not in SCENE_INTENTS:
                raise ValueError(f"unknown scene intent in template useFor: {intent!r}")
        return value


class ReferenceAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=512)
    role: Literal["composition", "positive_example", "negative_example", "guide", "reference", "palette"] = (
        "reference"
    )


class PresetAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=512)
    role: Literal["palette", "style", "template", "other"] = "other"


class ProviderDependency(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    version: str = Field(default="", max_length=64)
    required: bool = False


class SkillDependency(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    version: str = Field(default="", max_length=64)
    required: Literal[False] = False
    role: Literal["advisory"] = "advisory"


class Dependencies(BaseModel):
    model_config = ConfigDict(extra="forbid")
    providers: list[ProviderDependency] = Field(default_factory=list, max_length=100)
    skills: list[SkillDependency] = Field(default_factory=list, max_length=100)


class FallbackPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    missingOptionalProvider: Literal["continue", "block"] = "continue"
    missingRequiredProvider: Literal["block"] = "block"
    providerFailure: Literal["next_declared", "block", "review"] = "next_declared"
    exhaustedProviders: Literal["review", "block"] = "review"


class DirectorPackManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["videoforge.director-pack"]
    formatVersion: Literal[1]
    id: str = Field(pattern=PACK_ID)
    version: str = Field(pattern=SEMVER)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    publisher: Publisher
    compatibility: Compatibility
    scenePolicy: ScenePolicy = Field(default_factory=ScenePolicy)
    routing: RoutingPolicy
    style: StylePolicy
    rhythm: RhythmPolicy
    continuity: ContinuityPolicy
    candidates: CandidatePolicy
    approval: ApprovalPolicy
    durationPolicy: DurationPolicy
    templates: list[TemplateReference] = Field(default_factory=list, max_length=100)
    references: list[ReferenceAsset] = Field(default_factory=list, max_length=100)
    presets: list[PresetAsset] = Field(default_factory=list, max_length=50)
    dependencies: Dependencies
    fallback: FallbackPolicy
    editable: list[str] = Field(default_factory=list, max_length=32)
    derivedFrom: PackIdentity | None = None


# ── Resolved Director Policy (read-only run snapshot) ──

SOURCE_TRUST = Literal["LOCAL", "UNVERIFIED", "TRUSTED_BUILTIN"]
POLICY_STATUS = Literal["enabled", "enabled_with_degradation", "blocked"]


class ResolvedPackIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    version: str
    manifestDigest: str = ""
    archiveDigest: str = ""
    sourceTrust: SOURCE_TRUST = "LOCAL"


class ResolvedProvider(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    version: str
    trust: SOURCE_TRUST = "UNVERIFIED"
    ready: bool = True


class EffectiveApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["auto", "review"] = "auto"
    forceReview: bool = False
    allowTrustedLocal: bool = True
    allowExternal: bool = False


class ResolvedAuthorization(BaseModel):
    model_config = ConfigDict(extra="forbid")
    externalAllowed: bool = False
    paidAllowed: bool = False
    maxCostPerRun: float = 0.0


class ResolvedReferenceAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    role: str


class ResolvedDirectorPolicy(BaseModel):
    """Immutable, stateless policy snapshot for a single run.

    May be attached to batch/item manifests for recovery and audit but never
    contains Scene, candidate, binding or timeline data.
    """

    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal[1] = 1
    compilerVersion: str = "1.0.0"
    pack: ResolvedPackIdentity
    providers: list[ResolvedProvider] = Field(default_factory=list)
    skills: list[dict] = Field(default_factory=list)
    effectiveRouting: dict[str, list[str]] = Field(default_factory=dict)
    effectiveApproval: EffectiveApproval = Field(default_factory=EffectiveApproval)
    effectiveStyle: dict = Field(default_factory=dict)
    effectiveReferences: list[ResolvedReferenceAsset] = Field(default_factory=list)
    authorization: ResolvedAuthorization = Field(default_factory=ResolvedAuthorization)
    degradations: list[str] = Field(default_factory=list)
    status: POLICY_STATUS = "enabled"
    resolvedAt: str = ""
    # Runtime strategy facts consumed by the Factory orchestrator.  These are
    # policy-only extensions beyond the protocol minimum; they still carry no
    # Project/Scene/binding/timeline state.
    candidateCount: int = Field(default=1, ge=1, le=4)
    motionPreference: Literal["static", "gentle", "dynamic"] = "static"
    durationPolicyVideo: Literal["exact", "crop", "loop", "speed_adjust", "reject"] = "reject"
    continuityAnchor: str = ""
