"""Compile the single immutable Resolved Director Policy for a run.

The resolver reads only the installed immutable Manifest, intersects the
registered Provider/Skill reality with the caller's run mode and
authorization, removes unavailable routes without inventing replacements,
applies only manifest-declared fallback order, computes the effective
approval and freezes the snapshot. It never modifies Project, VisualPlan,
Scene timing or Timeline state.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from models.director_pack import (
    DirectorPackManifest,
    EffectiveApproval,
    ResolvedAuthorization,
    ResolvedDirectorPolicy,
    ResolvedPackIdentity,
    ResolvedProvider,
    ResolvedReferenceAsset,
)
from services import director_pack_store as store
from shared.director_intents import SCENE_INTENTS
from visual_providers.registry import list_providers

COMPILER_VERSION = "1.0.0"
DIRECTOR_PROTOCOL_PREFIX = "1."


class DirectorPackResolveError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _normalize_authorization(authorization: dict[str, Any] | None) -> ResolvedAuthorization:
    payload = authorization or {}
    return ResolvedAuthorization(
        externalAllowed=bool(payload.get("externalAllowed", False)),
        paidAllowed=bool(payload.get("paidAllowed", False)),
        maxCostPerRun=float(payload.get("maxCostPerRun", 0.0) or 0.0),
    )


def _provider_registry() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in list_providers():
        provider_id = str(item.get("providerId") or "")
        if provider_id:
            index[provider_id] = item
    return index


def _validate_preset_yaml(path: Path) -> None:
    """Preset YAML must be plain data: mapping/list/scalar, no custom tags."""
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise DirectorPackResolveError(
            "preset_invalid_yaml", f"preset is not valid YAML: {path.name}: {exc}"
        ) from exc
    if parsed is not None and not isinstance(parsed, (dict, list, str, int, float, bool)):
        raise DirectorPackResolveError(
            "preset_invalid_yaml", f"preset must contain plain data only: {path.name}"
        )


def resolve(
    manifest: DirectorPackManifest,
    run_mode: str,
    authorization: dict[str, Any] | None = None,
    installed_dir: Path | None = None,
) -> ResolvedDirectorPolicy:
    """Compile the frozen policy from an immutable Manifest."""
    auth = _normalize_authorization(authorization)
    degradations: list[str] = []
    registry = _provider_registry()

    # 1. Protocol compatibility
    if not manifest.compatibility.directorProtocol.startswith(DIRECTOR_PROTOCOL_PREFIX):
        raise DirectorPackResolveError(
            "incompatible_protocol",
            f"unsupported director protocol: {manifest.compatibility.directorProtocol!r}",
        )

    # 2. Resolve registered providers to exact versions / trust / templates.
    declared = {dep.id: dep for dep in manifest.dependencies.providers}
    resolved_providers: list[ResolvedProvider] = []
    available: set[str] = set()
    for provider_id, dep in sorted(declared.items()):
        meta = registry.get(provider_id)
        if meta is None:
            degradations.append(f"provider_missing:{provider_id}")
            if dep.required:
                # Missing required provider blocks the whole policy.
                degradations.append(f"provider_missing_required:{provider_id}")
            continue
        resolved_providers.append(
            ResolvedProvider(
                id=provider_id,
                version=str(meta.get("version") or ""),
                trust=str(meta.get("trust") or "UNVERIFIED"),
                ready=True,
            )
        )
        available.add(provider_id)

    # 3. Resolve advisory Skills (v1 always advisory-only, may be empty).
    skills = [
        {"id": skill.id, "version": skill.version, "role": skill.role}
        for skill in manifest.dependencies.skills
    ]

    # 4. Effective routing: remove unavailable routes, never invent providers.
    effective_routing: dict[str, list[str]] = {}
    for intent in SCENE_INTENTS:
        declared_route = manifest.routing.intents.get(intent) or manifest.routing.default
        effective_routing[intent] = [p for p in declared_route if p in available]

    # 5. Validate template references against the registered template catalog.
    registered_templates: set[str] = set()
    for provider in resolved_providers:
        meta = registry.get(provider.id) or {}
        registered_templates.update(str(item) for item in meta.get("templateIds") or [])
    for template in manifest.templates:
        if template.id not in registered_templates:
            degradations.append(f"template_missing:{template.id}")

    # 6. Validate reference and preset assets against the installed directory.
    effective_references: list[ResolvedReferenceAsset] = []
    for reference in manifest.references:
        if installed_dir is not None and not (installed_dir / reference.path).is_file():
            degradations.append(f"reference_missing:{reference.path}")
        effective_references.append(
            ResolvedReferenceAsset(path=reference.path, role=str(reference.role))
        )
    for preset in manifest.presets:
        if installed_dir is not None:
            preset_path = installed_dir / preset.path
            if not preset_path.is_file():
                degradations.append(f"reference_missing:{preset.path}")
            else:
                _validate_preset_yaml(preset_path)
        effective_references.append(
            ResolvedReferenceAsset(path=preset.path, role=str(preset.role))
        )

    # 7. Intersect user run mode, provider trust, permission and cost.
    force_review = run_mode == "review"
    has_fallback = any(item.startswith("provider_missing") for item in degradations)
    has_warning = bool(degradations)
    untrusted = any(provider.trust != "TRUSTED_BUILTIN" for provider in resolved_providers)
    external_or_paid = auth.externalAllowed or auth.paidAllowed or auth.maxCostPerRun > 0
    if has_fallback or has_warning or untrusted or external_or_paid:
        force_review = True

    # 8. Effective approval: REVIEW can never be weakened to AUTO.
    if run_mode == "review" or force_review:
        approval_mode = "review"
    else:
        approval_mode = manifest.approval.defaultMode
    effective_approval = EffectiveApproval(
        mode=approval_mode,
        forceReview=force_review,
        allowTrustedLocal=manifest.approval.auto.allowTrustedLocal,
        allowExternal=manifest.approval.auto.allowExternal,
    )

    # 9. Status: block when no usable route remains or a required provider is gone.
    any_route = any(route for route in effective_routing.values())
    required_missing = any(item.startswith("provider_missing_required:") for item in degradations)
    if required_missing or not any_route:
        status = "blocked"
    elif degradations:
        status = "enabled_with_degradation"
    else:
        status = "enabled"

    return ResolvedDirectorPolicy(
        pack=ResolvedPackIdentity(
            id=manifest.id,
            version=manifest.version,
            sourceTrust="LOCAL",
        ),
        providers=resolved_providers,
        skills=skills,
        effectiveRouting=effective_routing,
        effectiveApproval=effective_approval,
        effectiveStyle={
            "anchor": manifest.style.anchor,
            "avoid": list(manifest.style.avoid),
        },
        effectiveReferences=effective_references,
        authorization=auth,
        degradations=degradations,
        status=status,
        resolvedAt=datetime.now(timezone.utc).isoformat(),
    )


def resolve_installed(
    pack_id: str, version: str, run_mode: str, authorization: dict[str, Any] | None = None
) -> ResolvedDirectorPolicy:
    """Resolve the immutable installed manifest into a frozen policy."""
    record = store.get_pack(pack_id, version)
    manifest = DirectorPackManifest.model_validate(record["manifest"])
    installed_dir = store._install_dir(pack_id, version)
    policy = resolve(manifest, run_mode, authorization, installed_dir=installed_dir)
    # Fill the authoritative digests/trust from the installation record.
    policy.pack = ResolvedPackIdentity(
        id=policy.pack.id,
        version=policy.pack.version,
        manifestDigest=str(record.get("manifestDigest") or ""),
        archiveDigest=str(record.get("archiveDigest") or ""),
        sourceTrust=str(record.get("sourceTrust") or "LOCAL"),
    )
    return policy


def policy_digest(policy: ResolvedDirectorPolicy) -> str:
    """Deterministic sha256 digest of the frozen policy JSON."""
    import hashlib

    payload = json.dumps(policy.model_dump(), sort_keys=True, ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()
