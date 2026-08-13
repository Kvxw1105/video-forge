"""Built-in autonomous production profiles and policy compilation."""
from __future__ import annotations

from copy import deepcopy

from models.production_profile import ProductionProfile, ProductionProfileSummary


_PROFILES: dict[str, ProductionProfile] = {
    "knowledge_explainer": ProductionProfile(
        id="knowledge_explainer",
        name="Knowledge Explainer",
        description="结构化知识解释，优先机制、因果、流程和拓扑视觉。",
        routingMode="code_visual",
        preferredProviders=["code_visual"],
        fallbackOrder=["code_visual", "stickman"],
        candidateCount=1,
        autoApprovalPolicy="local_only",
        codeVisualTheme="clean editorial diagram, cinematic low-saturation warm palette",
        motionPreference="auto",
        visualDensity="balanced",
    ),
    "psychology_cognition": ProductionProfile(
        id="psychology_cognition",
        name="Psychology / Cognition",
        description="心理与认知叙事，优先关系、冲突、象征性人物场景。",
        routingMode="stickman",
        preferredProviders=["stickman", "code_visual"],
        fallbackOrder=["stickman", "code_visual"],
        candidateCount=1,
        autoApprovalPolicy="local_only",
        codeVisualTheme="symbolic psychology diagram, warm paper, restrained contrast",
        motionPreference="auto",
        visualDensity="sparse",
    ),
    "balanced_auto": ProductionProfile(
        id="balanced_auto",
        name="Balanced Auto",
        description="让 Auto Router 按 Scene 语义在本地 Provider 之间判断。",
        routingMode="auto",
        preferredProviders=["code_visual", "stickman"],
        fallbackOrder=["code_visual", "stickman"],
        candidateCount=1,
        autoApprovalPolicy="local_only",
        motionPreference="auto",
        visualDensity="balanced",
    ),
}


def list_profiles() -> list[ProductionProfileSummary]:
    return [ProductionProfileSummary(**{key: value for key, value in profile.model_dump().items() if key in ProductionProfileSummary.model_fields}) for profile in _PROFILES.values()]


def get_profile(profile_id: str | None) -> ProductionProfile:
    key = str(profile_id or "balanced_auto").strip().lower()
    profile = _PROFILES.get(key) or _PROFILES["balanced_auto"]
    return profile.model_copy(deep=True)


def compile_profile(profile_id: str | None, overrides: dict | None = None) -> ProductionProfile:
    """Compile a profile plus safe user policy overrides into one immutable value."""
    profile = get_profile(profile_id)
    allowed = set(ProductionProfile.model_fields)
    patch = {key: value for key, value in (overrides or {}).items() if key in allowed}
    return profile.model_copy(update=deepcopy(patch))
