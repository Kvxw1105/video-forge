"""Factory-facing orchestration over the existing Visual Generation lifecycle.

This module deliberately contains no renderer code.  It consumes a unified
``EffectiveVisualPolicy`` (compiled either from a legacy ProductionProfile or
from a frozen Resolved Director Policy), compiles it into image-generation
requests, runs the registered local providers, optionally applies an auditable
auto-approval policy, and returns a pause/continue decision to the durable
TemplateBatch manifest.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from models.production_profile import ProductionProfile
from models.director_pack import ResolvedDirectorPolicy
from services import image_generation_service as visuals
from services.director_policy_resolver import policy_digest
from services.project_service import get_project
from visual_providers.contracts import SceneRequest
from visual_providers.router import route_scene


@dataclass(frozen=True)
class FactoryVisualResult:
    outcome: Literal["bound", "awaiting_visual_approval"]
    batches: tuple[dict, ...]
    primary_batch_id: str
    policy: "EffectiveVisualPolicy"


@dataclass(frozen=True)
class EffectiveVisualPolicy:
    """Unified read-only visual policy consumed by the Factory orchestrator.

    Only routing, fallback, candidate count, style, continuity, motion,
    duration and approval are read here.  Never Scene timing, bindings or
    generated assets.
    """

    source: str
    routing_mode: str = "auto"
    intent_routes: dict[str, tuple[str, ...]] | None = None
    fallback_order: tuple[str, ...] = ()
    candidate_count: int = 1
    style_anchor: str = ""
    code_visual_theme: str = ""
    continuity_anchor: str = ""
    motion_preference: Literal["static", "motion"] = "static"
    duration_policy: str = "exact"
    approval_mode: Literal["auto", "review"] = "review"
    force_review: bool = False
    can_auto: bool = False
    audit_prefix: str = ""
    policy_digest: str = ""

    def provider_chain(self, rules_hit: tuple[str, ...]) -> tuple[str, ...]:
        if not self.intent_routes:
            return ()
        for intent in rules_hit:
            chain = self.intent_routes.get(intent)
            if chain:
                return chain
        return self.intent_routes.get("generic", ())


def resolved_policy_from_profile(profile: ProductionProfile) -> EffectiveVisualPolicy:
    """Adapter: legacy ProductionProfile -> unified policy (V3 behaviour)."""
    can_auto = (
        profile.autoApprovalPolicy in {"always", "local_only"}
        and profile.externalPolicy == "local_only"
    )
    return EffectiveVisualPolicy(
        source=f"profile:{profile.id}",
        routing_mode=profile.routingMode,
        fallback_order=tuple(profile.fallbackOrder),
        candidate_count=profile.candidateCount,
        style_anchor=profile.styleAnchor or profile.codeVisualTheme,
        code_visual_theme=profile.codeVisualTheme,
        continuity_anchor=profile.continuityAnchor,
        motion_preference="static" if profile.motionPreference == "static" else "motion",
        duration_policy=profile.durationPolicy,
        approval_mode="auto" if can_auto else "review",
        force_review=False,
        can_auto=can_auto,
        audit_prefix=f"profile:{profile.id}",
        policy_digest=f"profile:{profile.id}",
    )


def effective_policy_from_director(policy: ResolvedDirectorPolicy) -> EffectiveVisualPolicy:
    """Adapter: frozen Resolved Director Policy -> unified policy."""
    can_auto = (
        policy.effectiveApproval.mode == "auto"
        and not policy.effectiveApproval.forceReview
        and all(provider.trust == "TRUSTED_BUILTIN" for provider in policy.providers)
    )
    return EffectiveVisualPolicy(
        source=f"director_pack:{policy.pack.id}",
        routing_mode="auto",
        intent_routes={
            intent: tuple(chain) for intent, chain in policy.effectiveRouting.items() if chain
        },
        fallback_order=tuple(
            dict.fromkeys(
                provider
                for chain in policy.effectiveRouting.values()
                for provider in chain
            )
        ),
        candidate_count=policy.candidateCount,
        style_anchor=str(policy.effectiveStyle.get("anchor") or ""),
        code_visual_theme=str(policy.effectiveStyle.get("anchor") or ""),
        continuity_anchor=policy.continuityAnchor,
        motion_preference="static" if policy.motionPreference == "static" else "motion",
        duration_policy=policy.durationPolicyVideo,
        approval_mode=policy.effectiveApproval.mode,
        force_review=policy.effectiveApproval.forceReview,
        can_auto=can_auto,
        audit_prefix=f"director_pack:{policy.pack.id}",
        policy_digest=policy_digest(policy),
    )


def _scene_overrides(policy: EffectiveVisualPolicy, workflow: dict) -> dict[str, dict]:
    overrides = {
        str(scene_id): dict(value or {})
        for scene_id, value in (workflow.get("sceneOverrides") or {}).items()
        if isinstance(value, dict)
    }
    output_mode = "static" if policy.motion_preference == "static" else "video"
    for value in overrides.values():
        value.setdefault("styleAnchor", policy.style_anchor)
        value.setdefault("continuityAnchor", policy.continuity_anchor)
        value.setdefault("durationPolicy", policy.duration_policy)
        value.setdefault("outputMode", output_mode)
    return overrides


def _intent_for_scene(project, scene, text: str) -> tuple[str, ...]:
    """Reuse the shared Router rules as Scene intent evidence."""
    plan = project.structuredContent.episode.visualPlan
    request = SceneRequest(
        project_id=project.id,
        visual_plan_id=plan.planId if hasattr(plan, "planId") else str(plan.get("planId")),
        scene_id=scene.id,
        block_id=scene.blockId,
        subtitle_ids=tuple(scene.subtitleIds),
        text=text,
        start=0,
        end=1,
        duration=1,
        input_hash="0" * 64,
        aspect_ratio=project.canvas.ratio,
        width=270,
        height=480,
        options={
            "finalPrompt": scene.summary or text,
            "semanticIntent": scene.summary or "",
            "routeHints": dict((scene.metadata or {}).get("semantic") or {}),
        },
    )
    return route_scene(request, "auto", "").rules_hit


def _apply_intent_routes(
    project,
    policy: EffectiveVisualPolicy,
    overrides: dict[str, dict],
    *,
    scene_ids: list[str] | None,
    provider_index: int = 0,
) -> dict[str, dict]:
    plan = project.structuredContent.episode.visualPlan
    if plan is None or not policy.intent_routes:
        return overrides
    scenes = plan.scenes if hasattr(plan, "scenes") else plan["scenes"]
    target = set(scene_ids or [])
    subtitle_by_id = {subtitle.id: subtitle for subtitle in project.subtitles}
    for scene in scenes:
        if target and scene.id not in target:
            continue
        subtitles = [subtitle_by_id[value] for value in scene.subtitleIds if value in subtitle_by_id]
        text = "".join(value.text for value in subtitles)
        chain = policy.provider_chain(_intent_for_scene(project, scene, text))
        if chain and provider_index < len(chain):
            overrides.setdefault(scene.id, {})["providerId"] = chain[provider_index]
    return overrides


def _create_and_run(
    project_id: str,
    policy: EffectiveVisualPolicy,
    *,
    scene_ids: list[str] | None,
    workflow: dict,
    routing_mode: str | None = None,
    provider_index: int = 0,
) -> dict:
    overrides = _scene_overrides(policy, workflow)
    project = get_project(project_id)
    plan = project.structuredContent.episode.visualPlan if project and project.structuredContent else None
    if plan:
        output_mode = "static" if policy.motion_preference == "static" else "video"
        target_ids = set(scene_ids or [scene.id for scene in plan.scenes])
        for scene in plan.scenes:
            if scene.id not in target_ids:
                continue
            values = overrides.setdefault(scene.id, {})
            values.setdefault("styleAnchor", policy.style_anchor)
            values.setdefault("continuityAnchor", policy.continuity_anchor)
            values.setdefault("durationPolicy", policy.duration_policy)
            values.setdefault("outputMode", output_mode)
    # Director Packs route each Scene by its shared-Router intent evidence;
    # legacy profiles keep the existing routing_mode semantics.
    if policy.intent_routes and project and project.structuredContent:
        overrides = _apply_intent_routes(
            project, policy, overrides, scene_ids=scene_ids, provider_index=provider_index
        )
    created = visuals.create_batch(
        project_id,
        channel="local",
        provider_id="",
        size=str(workflow.get("size") or ""),
        candidate_count=int(policy.candidate_count),
        routing_mode=routing_mode or policy.routing_mode,
        auto_approve=False,
        style_anchor=policy.style_anchor or policy.code_visual_theme,
        continuity_anchor=policy.continuity_anchor,
        scene_ids=scene_ids,
        scene_overrides=overrides,
    )
    return visuals.run_local_batch(project_id, created["batchId"])


def run_factory_visuals(
    project_id: str,
    spec,
    *,
    workflow: dict,
    update=None,
) -> FactoryVisualResult:
    policy = workflow.get("compiledPolicy")
    if not isinstance(policy, EffectiveVisualPolicy):
        raise ValueError("Factory visual workflow requires a compiled EffectiveVisualPolicy")

    if update:
        update("selecting_visual_provider", "选择视觉 Provider")
    primary = _create_and_run(project_id, policy, scene_ids=None, workflow=workflow)
    batches = [primary]

    # Local fallback is intentionally a second request for only failed Scenes;
    # successful candidates and their input hashes are retained in the first
    # batch.  This keeps recovery incremental and makes the decision auditable.
    failed = [item for item in primary.get("items", []) if item.get("status") == "failed"]
    if failed:
        if policy.intent_routes:
            # Director Pack fallback: only the manifest-declared next item in
            # each Scene's intent chain, never an invented provider.
            next_index = 1
            if update:
                update("generating_visuals", f"Fallback {next_index}: 重跑 {len(failed)} 个失败 Scene")
            retry = _create_and_run(
                project_id,
                policy,
                scene_ids=[str(item["sceneId"]) for item in failed],
                workflow=workflow,
                provider_index=next_index,
            )
            batches.append(retry)
            failed = [item for item in retry.get("items", []) if item.get("status") == "failed"]
        else:
            for fallback_provider in policy.fallback_order:
                if fallback_provider == policy.routing_mode or fallback_provider not in {"stickman", "code_visual"}:
                    continue
                if not failed:
                    break
                if update:
                    update("generating_visuals", f"Fallback {fallback_provider}：重跑 {len(failed)} 个失败 Scene")
                retry = _create_and_run(
                    project_id,
                    policy,
                    scene_ids=[str(item["sceneId"]) for item in failed],
                    workflow=workflow,
                    routing_mode=fallback_provider,
                )
                batches.append(retry)
                failed = [item for item in retry.get("items", []) if item.get("status") == "failed"]

    generated = [
        item for batch in batches for item in batch.get("items", [])
        if item.get("status") in {"generated", "bound"} and item.get("candidates")
    ]
    if not generated:
        errors = [item.get("error") for batch in batches for item in batch.get("items", []) if item.get("error")]
        raise visuals.ImageGenerationError("visual_generation_failed", "; ".join(errors)[:500] or "No visual candidates were generated")

    can_auto_approve = (
        str(spec.productionMode or "review") == "auto"
        and policy.can_auto
    )
    if can_auto_approve:
        if update:
            update("binding_visuals", "自动批准本地候选并绑定 Scene")
        for batch in batches:
            selections = [
                {"sceneId": item["sceneId"], "candidateId": item["candidates"][0]["candidateId"]}
                for item in batch.get("items", [])
                if item.get("status") == "generated" and item.get("candidates")
            ]
            if selections:
                visuals.approve_candidates(
                    project_id,
                    batch["batchId"],
                    selections,
                    approval_policy=policy.audit_prefix,
                    approved_by="videoforge:auto",
                )
        return FactoryVisualResult("bound", tuple(batches), primary["batchId"], policy)

    return FactoryVisualResult("awaiting_visual_approval", tuple(batches), primary["batchId"], policy)
