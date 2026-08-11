"""Factory-facing orchestration over the existing Visual Generation lifecycle.

This module deliberately contains no renderer code.  It compiles a
ProductionProfile into image-generation requests, runs the registered local
providers, optionally applies an auditable auto-approval policy, and returns a
pause/continue decision to the durable TemplateBatch manifest.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from models.production_profile import ProductionProfile
from services import image_generation_service as visuals
from services.project_service import get_project


@dataclass(frozen=True)
class FactoryVisualResult:
    outcome: Literal["bound", "awaiting_visual_approval"]
    batches: tuple[dict, ...]
    primary_batch_id: str
    profile: ProductionProfile


def _scene_overrides(profile: ProductionProfile, workflow: dict) -> dict[str, dict]:
    overrides = {
        str(scene_id): dict(value or {})
        for scene_id, value in (workflow.get("sceneOverrides") or {}).items()
        if isinstance(value, dict)
    }
    output_mode = "static" if profile.motionPreference == "static" else "video"
    for value in overrides.values():
        value.setdefault("styleAnchor", profile.styleAnchor)
        value.setdefault("continuityAnchor", profile.continuityAnchor)
        value.setdefault("durationPolicy", profile.durationPolicy)
        value.setdefault("outputMode", output_mode)
    return overrides


def _create_and_run(
    project_id: str,
    profile: ProductionProfile,
    *,
    scene_ids: list[str] | None,
    workflow: dict,
    routing_mode: str | None = None,
) -> dict:
    overrides = _scene_overrides(profile, workflow)
    project = get_project(project_id)
    plan = project.structuredContent.episode.visualPlan if project and project.structuredContent else None
    if plan:
        output_mode = "static" if profile.motionPreference == "static" else "video"
        target_ids = set(scene_ids or [scene.id for scene in plan.scenes])
        for scene in plan.scenes:
            if scene.id not in target_ids:
                continue
            values = overrides.setdefault(scene.id, {})
            values.setdefault("styleAnchor", profile.styleAnchor)
            values.setdefault("continuityAnchor", profile.continuityAnchor)
            values.setdefault("durationPolicy", profile.durationPolicy)
            values.setdefault("outputMode", output_mode)
    # If a profile requests a specific provider, the shared Router still owns
    # semantic routing for auto mode; explicit modes remain user-visible.
    created = visuals.create_batch(
        project_id,
        channel="local",
        provider_id="",
        size=str(workflow.get("size") or ""),
        candidate_count=int(profile.candidateCount),
        routing_mode=routing_mode or profile.routingMode,
        auto_approve=False,
        style_anchor=profile.styleAnchor or profile.codeVisualTheme,
        continuity_anchor=profile.continuityAnchor,
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
    profile = workflow.get("compiledProfile")
    if not isinstance(profile, ProductionProfile):
        raise ValueError("Factory visual workflow requires a compiled ProductionProfile")

    if update:
        update("selecting_visual_provider", "选择视觉 Provider")
    primary = _create_and_run(project_id, profile, scene_ids=None, workflow=workflow)
    batches = [primary]

    # Local fallback is intentionally a second request for only failed Scenes;
    # successful candidates and their input hashes are retained in the first
    # batch.  This keeps recovery incremental and makes the decision auditable.
    failed = [item for item in primary.get("items", []) if item.get("status") == "failed"]
    if failed and profile.fallbackOrder:
        for fallback_provider in profile.fallbackOrder:
            if fallback_provider == profile.routingMode or fallback_provider not in {"stickman", "code_visual"}:
                continue
            if not failed:
                break
            if update:
                update("generating_visuals", f"Fallback {fallback_provider}：重跑 {len(failed)} 个失败 Scene")
            retry = _create_and_run(
                project_id,
                profile,
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
        and profile.autoApprovalPolicy in {"always", "local_only"}
        and profile.externalPolicy == "local_only"
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
                    approval_policy=f"profile:{profile.id}",
                    approved_by="videoforge:auto",
                )
        return FactoryVisualResult("bound", tuple(batches), primary["batchId"], profile)

    return FactoryVisualResult("awaiting_visual_approval", tuple(batches), primary["batchId"], profile)
