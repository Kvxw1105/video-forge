"""Declarative, executable Production Pack contracts for VideoForge.

Production Packs are data-only installation units.  They choose existing
renderers through an auditable compiler; they never contain executable code,
commands, local paths, or network URLs.  The module deliberately depends on
the existing Code Visual provider instead of introducing another asset or
preview runtime.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4


PACK_SCHEMA_VERSION = 2
VISUAL_SPEC_SCHEMA_VERSION = 1
PACK_EXPORT_FORMAT = "videoforge-production-pack"
PACK_EXPORT_VERSION = 2
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{1,95}$")
_EXECUTABLE_KEY = re.compile(r"(?:^|[_-])(code|script|command|executable|shell|process|path|url|endpoint)(?:$|[_-])", re.I)
_KNOWN_OUTPUTS = {"svg", "png", "video", "transparent_sequence"}
_KNOWN_PRESENTATIONS = {"main", "overlay"}
_KNOWN_THEMES = {"light", "dark"}


class ProductionPackError(ValueError):
    """Validation failure with a stable, API-safe error code."""

    def __init__(self, code: str, message: str, *, recoverable: bool = True, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.recoverable = recoverable
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "recoverable": self.recoverable, "details": deepcopy(self.details)}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _clone(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def pack_fingerprint(pack: dict[str, Any]) -> str:
    """Fingerprint only normalized declarative pack state, never timestamps."""
    ignored = {"createdAt", "updatedAt", "imported", "migration", "health", "lastEval", "source", "fingerprint"}
    stable = {key: value for key, value in pack.items() if key not in ignored}
    return hashlib.sha256(_canonical(stable).encode("utf-8")).hexdigest()


def _safe_identifier(value: Any, label: str) -> str:
    result = str(value or "").strip()
    if not _IDENTIFIER.fullmatch(result):
        raise ProductionPackError("invalid_identifier", f"{label} 必须是安全的 kebab-case 标识符。", details={"value": result})
    return result


def _assert_declarative(value: Any, path: str = "pack") -> None:
    """Reject payload shapes which could become execution instructions later."""
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            if _EXECUTABLE_KEY.search(key_text):
                raise ProductionPackError("unsafe_executable_field", f"不允许可执行或外部路径字段：{path}.{key_text}", details={"field": f"{path}.{key_text}"})
            _assert_declarative(child, f"{path}.{key_text}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_declarative(child, f"{path}[{index}]")
    elif isinstance(value, str):
        if len(value) > 12_000:
            raise ProductionPackError("value_too_large", f"{path} 超过允许长度。")
        if "\x00" in value:
            raise ProductionPackError("invalid_value", f"{path} 包含非法字符。")


def _style_kit(source: Any = None) -> dict[str, Any]:
    source = source if isinstance(source, dict) else {}
    palette = source.get("palette") if isinstance(source.get("palette"), dict) else {}
    return {
        "identity": {
            "name": str((source.get("identity") or {}).get("name") or source.get("name") or "Production Pack"),
            "keywords": list((source.get("identity") or {}).get("keywords") or []),
            "negativeKeywords": list((source.get("identity") or {}).get("negativeKeywords") or []),
        },
        "palette": {
            "background": str(palette.get("background") or "#171512"),
            "surface": str(palette.get("surface") or "#24201B"),
            "primary": str(palette.get("primary") or "#E8E0D2"),
            "secondary": str(palette.get("secondary") or "#B9A98F"),
            "accent": str(palette.get("accent") or "#B8956A"),
            "text": str(palette.get("text") or "#F5F1E8"),
            "muted": str(palette.get("muted") or "#8B8275"),
        },
        "typography": {
            "displayRole": str((source.get("typography") or {}).get("displayRole") or "Cormorant Garamond"),
            "bodyRole": str((source.get("typography") or {}).get("bodyRole") or "Crimson Pro"),
            "captionRole": str((source.get("typography") or {}).get("captionRole") or "system-ui"),
            "numericRole": str((source.get("typography") or {}).get("numericRole") or "ui-monospace"),
            "fallbacks": list((source.get("typography") or {}).get("fallbacks") or ["serif", "sans-serif"]),
        },
        "composition": {
            "density": str((source.get("composition") or {}).get("density") or "focused"),
            "alignment": str((source.get("composition") or {}).get("alignment") or "editorial-grid"),
            "safeArea": str((source.get("composition") or {}).get("safeArea") or "10%"),
            "subjectScale": str((source.get("composition") or {}).get("subjectScale") or "medium"),
            "informationHierarchy": str((source.get("composition") or {}).get("informationHierarchy") or "single-primary-relationship"),
        },
        "motion": {
            "tempo": str((source.get("motion") or {}).get("tempo") or "measured"),
            "entrance": str((source.get("motion") or {}).get("entrance") or "reveal"),
            "emphasis": str((source.get("motion") or {}).get("emphasis") or "relationship-first"),
            "exit": str((source.get("motion") or {}).get("exit") or "hold"),
            "easing": str((source.get("motion") or {}).get("easing") or "easeOutCubic"),
            "maxConcurrentMotion": int((source.get("motion") or {}).get("maxConcurrentMotion") or 3),
        },
        "surface": {
            "border": str((source.get("surface") or {}).get("border") or "hairline"),
            "corner": str((source.get("surface") or {}).get("corner") or "2px"),
            "shadow": str((source.get("surface") or {}).get("shadow") or "none"),
            "grain": str((source.get("surface") or {}).get("grain") or "subtle"),
            "glow": str((source.get("surface") or {}).get("glow") or "none"),
        },
        "prohibitions": list(source.get("prohibitions") or ["generic purple gradient", "meaningless particles", "oversized glass cards"]),
    }


def _binding(
    binding_id: str,
    renderer_id: str,
    template_id: str,
    *,
    theme: str,
    presentation: str,
    visual_family: str,
) -> dict[str, Any]:
    return {
        "bindingId": binding_id,
        "providerId": "code_visual_svg",
        "rendererId": renderer_id,
        "templateId": template_id,
        "outputMode": "video",
        "presentationMode": presentation,
        "themeMode": theme,
        "defaults": {"visualFamily": visual_family, "ipPack": "neutral", "videoFps": 12},
        "constraints": {"maxTextChars": 240},
        "requiresApproval": False,
        "estimatedCostClass": "local_free",
    }


def builtin_packs() -> dict[str, dict[str, Any]]:
    """First-party packs use only renderer/template combinations in the real registry."""
    skill = [{"skillId": "subtitle_scene_director", "version": 1}]
    knowledge = {
        "schemaVersion": PACK_SCHEMA_VERSION,
        "packId": "knowledge-structure-motion",
        "version": 1,
        "name": "知识结构动画",
        "description": "把因果、对比、流程与层级关系编译为可追溯的知识结构动画。",
        "recipeId": "structured-knowledge-video",
        "skillPins": skill,
        "styleKit": _style_kit({
            "identity": {"name": "Knowledge Structure Motion", "keywords": ["causal", "comparison", "flow", "network"], "negativeKeywords": ["decorative noise"]},
            "palette": {"background": "#F5F1E8", "surface": "#E7DED0", "primary": "#171717", "secondary": "#4D4A43", "accent": "#A52E28", "text": "#171717", "muted": "#716A5F"},
            "composition": {"density": "structured", "alignment": "diagram-grid", "safeArea": "10%", "subjectScale": "medium", "informationHierarchy": "cause-process-result"},
            "motion": {"tempo": "explanatory", "entrance": "staged-reveal", "emphasis": "relationship-progress", "exit": "hold", "easing": "easeOutCubic", "maxConcurrentMotion": 3},
            "surface": {"border": "ink-hairline", "corner": "0px", "shadow": "none", "grain": "paper-subtle", "glow": "none"},
        }),
        "rendererBindings": [
            _binding("knowledge-causal-primary", "mechanism_diagram", "mechanism_diagram:evidence", theme="light", presentation="main", visual_family="evidence"),
            _binding("knowledge-contrast-primary", "pixel_rules", "pixel_rules:trap_detection", theme="dark", presentation="main", visual_family="trap_detection"),
            _binding("knowledge-flow-primary", "white_sketch", "white_sketch:hidden_path", theme="dark", presentation="main", visual_family="hidden_path"),
            _binding("knowledge-network-primary", "mechanism_diagram", "mechanism_diagram:evidence", theme="light", presentation="main", visual_family="evidence"),
        ],
        "sceneArchetypes": [
            {"archetypeId": "causal-mechanism", "name": "因果机制", "semanticTags": ["因为", "导致", "原因", "结果", "机制", "影响", "如何发生"], "blockTypes": ["explanation"], "sceneIntents": ["causal"], "priority": 100, "rendererBindingId": "knowledge-causal-primary", "parameterDefaults": {}, "fallbackArchetypeId": "clear-information-card", "enabled": True},
            {"archetypeId": "comparative-judgment", "name": "对比判断", "semanticTags": ["区别", "对比", "相反", "优点", "缺点", "两类", "前后"], "blockTypes": ["comparison"], "sceneIntents": ["comparison"], "priority": 95, "rendererBindingId": "knowledge-contrast-primary", "parameterDefaults": {}, "fallbackArchetypeId": "clear-information-card", "enabled": True},
            {"archetypeId": "timeline-process", "name": "时间线流程", "semanticTags": ["第一步", "然后", "接着", "最后", "阶段", "过程", "演化"], "blockTypes": ["process"], "sceneIntents": ["process"], "priority": 90, "rendererBindingId": "knowledge-flow-primary", "parameterDefaults": {}, "fallbackArchetypeId": "clear-information-card", "enabled": True},
            {"archetypeId": "hierarchy-network", "name": "层级关系网络", "semanticTags": ["体系", "层级", "组成", "中心", "分支", "关系", "网络"], "blockTypes": ["hierarchy"], "sceneIntents": ["network"], "priority": 85, "rendererBindingId": "knowledge-network-primary", "parameterDefaults": {}, "fallbackArchetypeId": "clear-information-card", "enabled": True},
            {"archetypeId": "clear-information-card", "name": "清晰信息卡", "semanticTags": [], "blockTypes": [], "sceneIntents": [], "priority": 1, "rendererBindingId": "knowledge-causal-primary", "parameterDefaults": {}, "fallbackArchetypeId": None, "enabled": True},
        ],
        "evalCases": [
            {"caseId": "abstract-view", "name": "抽象观点", "text": "长期内耗会让注意力被情绪占满。", "ratio": "9:16"},
            {"caseId": "causal-explanation", "name": "因果解释", "text": "外部评价进入自我判断，因为比较不断放大期待与现实的落差。", "ratio": "9:16"},
            {"caseId": "comparison", "name": "两类对比", "text": "一种人反复比较，另一种人把评价拆成事实、解释和下一步。", "ratio": "9:16"},
            {"caseId": "process", "name": "多步骤流程", "text": "第一步记录评价，然后区分事实，最后形成一个可执行动作。", "ratio": "16:9"},
            {"caseId": "network", "name": "层级关系", "text": "一个体系由中心判断、外部评价、情绪反应和行动反馈组成。", "ratio": "9:16"},
        ],
        "capabilityIds": ["review_visual_scene_plan", "prepare_visual_generation_pack", "bind_scene_assets"],
        "providerPolicy": {"routes": ["local_free"], "allowNetwork": False, "allowPaid": False},
        "status": "installed",
        "source": {"type": "built_in"},
    }
    editorial = {
        "schemaVersion": PACK_SCHEMA_VERSION,
        "packId": "minimal-editorial",
        "version": 1,
        "name": "极简编辑部",
        "description": "以留白、短促节奏和叙事留白呈现同一段知识内容。",
        "recipeId": "structured-knowledge-video",
        "skillPins": skill,
        "styleKit": _style_kit({
            "identity": {"name": "Minimal Editorial", "keywords": ["editorial", "quiet", "reduced"], "negativeKeywords": ["dense diagrams"]},
            "palette": {"background": "#1A1814", "surface": "#28241E", "primary": "#F5F1E8", "secondary": "#CBBDA8", "accent": "#B8956A", "text": "#F5F1E8", "muted": "#978B7D"},
            "composition": {"density": "sparse", "alignment": "asymmetric-editorial", "safeArea": "14%", "subjectScale": "large", "informationHierarchy": "one-claim-per-beat"},
            "motion": {"tempo": "deliberate", "entrance": "quiet-reveal", "emphasis": "single-phrase", "exit": "linger", "easing": "easeInOutSine", "maxConcurrentMotion": 1},
            "surface": {"border": "matte-hairline", "corner": "0px", "shadow": "none", "grain": "fine-film", "glow": "none"},
        }),
        "rendererBindings": [
            _binding("editorial-primary", "white_sketch", "white_sketch:hidden_path", theme="dark", presentation="overlay", visual_family="hidden_path"),
            _binding("editorial-contrast", "silhouette", "silhouette:anxiety", theme="dark", presentation="main", visual_family="anxiety"),
        ],
        "sceneArchetypes": [
            {"archetypeId": "editorial-tension", "name": "编辑部张力", "semanticTags": ["内耗", "比较", "评价", "期待", "压力", "困住"], "blockTypes": [], "sceneIntents": ["tension"], "priority": 90, "rendererBindingId": "editorial-contrast", "parameterDefaults": {"overlayScale": 0.42}, "fallbackArchetypeId": "editorial-note", "enabled": True},
            {"archetypeId": "editorial-note", "name": "编辑部留白", "semanticTags": [], "blockTypes": [], "sceneIntents": [], "priority": 1, "rendererBindingId": "editorial-primary", "parameterDefaults": {"overlayScale": 0.34}, "fallbackArchetypeId": None, "enabled": True},
        ],
        "evalCases": _clone(knowledge["evalCases"]),
        "capabilityIds": ["review_visual_scene_plan", "prepare_visual_generation_pack", "bind_scene_assets"],
        "providerPolicy": {"routes": ["local_free"], "allowNetwork": False, "allowPaid": False},
        "status": "installed",
        "source": {"type": "built_in"},
    }
    for pack in (knowledge, editorial):
        pack["fingerprint"] = pack_fingerprint(pack)
    return {knowledge["packId"]: knowledge, editorial["packId"]: editorial}


def renderer_registry() -> dict[str, Any]:
    """Expose installed renderer capabilities as the sole ID authority."""
    from visual_assets.registry import PROVIDERS
    from visual_assets.rasterizer import ResvgSvgRasterizer
    from visual_assets.code_visual.provider import FAMILIES
    from visual_assets.code_visual.renderers import REGISTRY

    ffmpeg = shutil.which("ffmpeg") is not None
    rasterizer_available = ResvgSvgRasterizer().is_available()
    code_visual_families = tuple(FAMILIES)
    entries: list[dict[str, Any]] = []
    for provider_id, provider in sorted(PROVIDERS.items()):
        if provider_id == "code_visual_svg":
            for renderer_id in sorted(REGISTRY):
                dependencies = [
                    *([] if ffmpeg else ["ffmpeg"]),
                    *([] if rasterizer_available else ["resvg-py"]),
                ]
                entries.append({
                    "providerId": provider_id,
                    "rendererId": renderer_id,
                    "templateIds": [f"{renderer_id}:{family}" for family in code_visual_families],
                    "supportedOutputModes": sorted(_KNOWN_OUTPUTS),
                    "supportedPresentationModes": sorted(_KNOWN_PRESENTATIONS),
                    "supportedThemeModes": sorted(_KNOWN_THEMES),
                    "parameterSchema": {"visualFamily": {"enum": list(code_visual_families)}, "ipPack": {"enum": ["neutral", "xuanqi", "huicewolf", "ayin"]}, "videoFps": {"minimum": 6, "maximum": 30}},
                    "costClass": "local_free",
                    "requiresNetwork": False,
                    "requiresApproval": False,
                    "availability": "available" if not dependencies else "degraded",
                    "missingDependencies": dependencies,
                    "providerVersion": getattr(provider, "provider_version", "unknown"),
                })
        else:
            entries.append({
                "providerId": provider_id,
                "rendererId": "default",
                "templateIds": [],
                "supportedOutputModes": ["svg", "png"],
                "supportedPresentationModes": ["main"],
                "supportedThemeModes": ["light", "dark"],
                "parameterSchema": {},
                "costClass": "local_free",
                "requiresNetwork": False,
                "requiresApproval": False,
                "availability": "available",
                "missingDependencies": [],
                "providerVersion": getattr(provider, "provider_version", "unknown"),
            })
    return {"schemaVersion": 1, "generatedAt": _now(), "renderers": entries}


def _registry_index(registry: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(str(row["providerId"]), str(row["rendererId"])): row for row in registry.get("renderers") or [] if isinstance(row, dict)}


def migrate_v1_pack(pack: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalise old Director Packs without overwriting their source file."""
    source = _clone(pack)
    if int(source.get("schemaVersion") or 1) >= PACK_SCHEMA_VERSION:
        normalized = _clone(source)
        normalized["schemaVersion"] = PACK_SCHEMA_VERSION
        normalized["styleKit"] = _style_kit(normalized.get("styleKit"))
        normalized.setdefault("rendererBindings", [])
        normalized.setdefault("sceneArchetypes", [])
        normalized.setdefault("evalCases", [])
        normalized.setdefault("providerPolicy", {"routes": ["local_free"], "allowNetwork": False, "allowPaid": False})
        return normalized, list((source.get("migration") or {}).get("warnings") or [])
    old_style = source.get("style") if isinstance(source.get("style"), dict) else {}
    template_values = [str(item) for item in source.get("templates") or [] if str(item).strip()]
    renderer = next((item for item in template_values if item in {"white_sketch", "silhouette", "pixel_rules", "mechanism_diagram"}), "mechanism_diagram")
    binding_id = "legacy-default"
    legacy = {
        "schemaVersion": PACK_SCHEMA_VERSION,
        "packId": str(source.get("packId") or "legacy-pack"),
        "version": int(source.get("version") or 1),
        "name": str(source.get("name") or "旧版导演包"),
        "description": str(source.get("description") or ""),
        "recipeId": str(source.get("recipeId") or "structured-knowledge-video"),
        "skillPins": list(source.get("skillPins") or []),
        "styleKit": _style_kit({"name": old_style.get("name"), "palette": {"background": old_style.get("palette") or "#171512"}, "identity": {"keywords": [old_style.get("mood")] if old_style.get("mood") else []}, "composition": {"alignment": old_style.get("layout") or "editorial-grid"}}),
        "rendererBindings": [_binding(binding_id, renderer, f"{renderer}:evidence", theme="light" if renderer == "mechanism_diagram" else "dark", presentation="main", visual_family="evidence")],
        "sceneArchetypes": [{"archetypeId": "legacy-information-card", "name": "旧版信息场景", "semanticTags": [], "blockTypes": [], "sceneIntents": [], "priority": 1, "rendererBindingId": binding_id, "parameterDefaults": {}, "fallbackArchetypeId": None, "enabled": True}],
        "evalCases": [],
        "capabilityIds": list(source.get("capabilityIds") or []),
        "providerPolicy": {"routes": ["local_free"], "allowNetwork": False, "allowPaid": False},
        "status": str(source.get("status") or "installed"),
        "createdAt": source.get("createdAt"),
        "updatedAt": source.get("updatedAt"),
        "imported": bool(source.get("imported")),
        "migration": {"fromSchemaVersion": int(source.get("schemaVersion") or 1), "warnings": ["已在内存中迁移 V1 Director Pack；主动保存后才会写入 V2 Manifest。"]},
    }
    return legacy, list(legacy["migration"]["warnings"])


class ProductionPackCompiler:
    """Validates Packs and compiles deterministic scene-level VisualSpecs."""

    def __init__(self, registry_loader: Callable[[], dict[str, Any]] = renderer_registry):
        self.registry_loader = registry_loader

    def normalize(self, pack: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        if not isinstance(pack, dict):
            raise ProductionPackError("pack_invalid", "Production Pack 必须是对象。")
        _assert_declarative(pack)
        normalized, warnings = migrate_v1_pack(pack)
        normalized["packId"] = _safe_identifier(normalized.get("packId"), "packId")
        normalized["version"] = max(1, int(normalized.get("version") or 1))
        normalized["name"] = str(normalized.get("name") or "").strip()[:120]
        normalized["description"] = str(normalized.get("description") or "").strip()[:800]
        normalized["fingerprint"] = pack_fingerprint(normalized)
        return normalized, warnings

    def validate(
        self,
        pack: dict[str, Any],
        *,
        capabilities: set[str] | None = None,
        skill_lookup: Callable[[str, int], dict[str, Any]] | None = None,
        require_eval_cases: bool = False,
    ) -> dict[str, Any]:
        errors: list[dict[str, Any]] = []
        warnings: list[str] = []
        try:
            normalized, migration_warnings = self.normalize(pack)
            warnings.extend(migration_warnings)
        except ProductionPackError as exc:
            return {"ok": False, "errors": [exc.as_dict()], "warnings": [], "pack": None}
        if not normalized["name"]:
            errors.append({"code": "pack_name_required", "message": "Production Pack 名称不能为空。"})
        registry = self.registry_loader()
        index = _registry_index(registry)
        bindings = normalized.get("rendererBindings") if isinstance(normalized.get("rendererBindings"), list) else []
        binding_ids: set[str] = set()
        for row in bindings:
            if not isinstance(row, dict):
                errors.append({"code": "binding_invalid", "message": "Renderer Binding 必须是对象。"}); continue
            try:
                binding_id = _safe_identifier(row.get("bindingId"), "bindingId")
            except ProductionPackError as exc:
                errors.append(exc.as_dict()); continue
            if binding_id in binding_ids:
                errors.append({"code": "duplicate_binding_id", "message": f"重复 Binding：{binding_id}"})
            binding_ids.add(binding_id)
            key = (str(row.get("providerId") or ""), str(row.get("rendererId") or ""))
            renderer = index.get(key)
            if renderer is None:
                errors.append({"code": "renderer_not_registered", "message": f"未注册 Renderer：{key[0]}/{key[1]}", "details": {"bindingId": binding_id}}); continue
            if row.get("outputMode") not in renderer["supportedOutputModes"]:
                errors.append({"code": "output_mode_unsupported", "message": f"Renderer 不支持输出模式：{row.get('outputMode')}", "details": {"bindingId": binding_id}})
            if row.get("presentationMode") not in renderer["supportedPresentationModes"]:
                errors.append({"code": "presentation_mode_unsupported", "message": f"Renderer 不支持呈现方式：{row.get('presentationMode')}", "details": {"bindingId": binding_id}})
            if row.get("themeMode") not in renderer["supportedThemeModes"]:
                errors.append({"code": "theme_mode_unsupported", "message": f"Renderer 不支持主题：{row.get('themeMode')}", "details": {"bindingId": binding_id}})
            template = row.get("templateId")
            if template is not None and str(template) not in renderer["templateIds"]:
                errors.append({"code": "template_not_registered", "message": f"Template 不属于真实 Registry：{template}", "details": {"bindingId": binding_id}})
            if renderer.get("availability") != "available":
                warnings.append(f"{binding_id} 缺少依赖：{', '.join(renderer.get('missingDependencies') or [])}")
        if not bindings:
            errors.append({"code": "renderer_bindings_required", "message": "至少需要一个 Renderer Binding。"})
        archetypes = normalized.get("sceneArchetypes") if isinstance(normalized.get("sceneArchetypes"), list) else []
        ids: set[str] = set()
        by_id: dict[str, dict[str, Any]] = {}
        for row in archetypes:
            if not isinstance(row, dict):
                errors.append({"code": "archetype_invalid", "message": "Scene Archetype 必须是对象。"}); continue
            try:
                archetype_id = _safe_identifier(row.get("archetypeId"), "archetypeId")
            except ProductionPackError as exc:
                errors.append(exc.as_dict()); continue
            if archetype_id in ids:
                errors.append({"code": "duplicate_archetype_id", "message": f"重复 Archetype：{archetype_id}"})
            ids.add(archetype_id); by_id[archetype_id] = row
            if str(row.get("rendererBindingId") or "") not in binding_ids:
                errors.append({"code": "binding_missing", "message": f"Archetype {archetype_id} 指向不存在的 Binding。"})
        for archetype_id, row in by_id.items():
            fallback = row.get("fallbackArchetypeId")
            if fallback and str(fallback) not in by_id:
                errors.append({"code": "fallback_missing", "message": f"Archetype {archetype_id} 的 fallback 不存在。"})
        for start in by_id:
            seen: set[str] = set(); current = start
            while current:
                if current in seen:
                    errors.append({"code": "fallback_cycle", "message": f"Archetype fallback 存在循环：{start}"}); break
                seen.add(current)
                current = str((by_id.get(current) or {}).get("fallbackArchetypeId") or "") or None
        if not archetypes:
            errors.append({"code": "archetypes_required", "message": "至少需要一个 Scene Archetype。"})
        if require_eval_cases and not normalized.get("evalCases"):
            errors.append({"code": "eval_cases_required", "message": "Pack Eval Kit 不能为空。"})
        if capabilities is not None:
            unknown = sorted(str(item) for item in normalized.get("capabilityIds") or [] if str(item) not in capabilities)
            if unknown:
                errors.append({"code": "capability_not_registered", "message": f"未注册能力：{', '.join(unknown)}"})
        if skill_lookup:
            for pin in normalized.get("skillPins") or []:
                try:
                    skill = skill_lookup(str(pin.get("skillId")), int(pin.get("version") or 1))
                    if skill.get("status") != "published":
                        errors.append({"code": "skill_not_published", "message": f"Skill 未发布：{skill.get('name') or pin.get('skillId')}"})
                except (KeyError, TypeError, ValueError):
                    errors.append({"code": "skill_pin_invalid", "message": "包含不存在的已固定 Skill 版本。"})
        return {"ok": not errors, "errors": errors, "warnings": sorted(set(warnings)), "pack": normalized, "registry": registry}

    @staticmethod
    def _scene_values(scene: dict[str, Any]) -> tuple[str, str | None, str | None]:
        meta = scene.get("metadata") if isinstance(scene.get("metadata"), dict) else {}
        semantic = meta.get("semantic") if isinstance(meta.get("semantic"), dict) else {}
        text = str(scene.get("text") or scene.get("summary") or "")
        block_type = str(scene.get("blockType") or semantic.get("blockType") or meta.get("blockType") or "") or None
        intent = str(scene.get("sceneIntent") or semantic.get("visualIntent") or meta.get("sceneIntent") or "") or None
        return text, block_type, intent

    def _select(self, pack: dict[str, Any], scene: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        text, block_type, intent = self._scene_values(scene)
        candidates: list[tuple[int, dict[str, Any], list[str], bool, bool]] = []
        for archetype in pack.get("sceneArchetypes") or []:
            if not archetype.get("enabled", True):
                continue
            tags = [str(tag) for tag in archetype.get("semanticTags") or [] if str(tag)]
            matched = [tag for tag in tags if tag.lower() in text.lower()]
            block_match = bool(block_type and block_type in {str(value) for value in archetype.get("blockTypes") or []})
            intent_match = bool(intent and intent in {str(value) for value in archetype.get("sceneIntents") or []})
            default = not tags and not archetype.get("blockTypes") and not archetype.get("sceneIntents")
            if matched or block_match or intent_match or default:
                score = int(archetype.get("priority") or 0) * 100 + len(matched) * 10 + int(block_match) * 4 + int(intent_match) * 4
                candidates.append((score, archetype, matched, block_match, intent_match))
        if not candidates:
            raise ProductionPackError("archetype_unresolved", "没有可用于当前 Scene 的 Archetype。", details={"sceneId": scene.get("sceneId") or scene.get("id")})
        candidates.sort(key=lambda row: (-row[0], str(row[1].get("archetypeId"))))
        _, archetype, matched, block_match, intent_match = candidates[0]
        evidence = {"source": "deterministic_pack_compiler", "matchedTags": matched, "matchedBlockType": block_type if block_match else None, "matchedSceneIntent": intent if intent_match else None}
        return archetype, evidence

    def compile(self, pack: dict[str, Any], scenes: list[dict[str, Any]], *, capabilities: set[str] | None = None, skill_lookup: Callable[[str, int], dict[str, Any]] | None = None) -> dict[str, Any]:
        checked = self.validate(pack, capabilities=capabilities, skill_lookup=skill_lookup)
        if not checked["ok"]:
            raise ProductionPackError("pack_compile_rejected", "Production Pack 未通过校验。", details={"errors": checked["errors"]})
        normalized = checked["pack"]
        bindings = {str(item["bindingId"]): item for item in normalized.get("rendererBindings") or []}
        compiled: list[dict[str, Any]] = []
        for order, source in enumerate(scenes, 1):
            scene = source if isinstance(source, dict) else {}
            scene_id = str(scene.get("sceneId") or scene.get("id") or f"scene_{order:03d}")
            archetype, evidence = self._select(normalized, scene)
            binding = bindings[str(archetype["rendererBindingId"])]
            parameters = {**dict(binding.get("defaults") or {}), **dict(archetype.get("parameterDefaults") or {})}
            visual_spec = {
                "schemaVersion": VISUAL_SPEC_SCHEMA_VERSION,
                "sceneId": scene_id,
                "packId": normalized["packId"],
                "packVersion": normalized["version"],
                "packFingerprint": normalized["fingerprint"],
                "archetypeId": archetype["archetypeId"],
                "rendererBindingId": binding["bindingId"],
                "providerId": binding["providerId"],
                "rendererId": binding["rendererId"],
                "templateId": binding.get("templateId"),
                "outputMode": binding["outputMode"],
                "presentationMode": binding["presentationMode"],
                "themeMode": binding["themeMode"],
                "styleTokens": _clone(normalized["styleKit"]),
                "parameters": _clone(parameters),
                "selectionEvidence": evidence,
            }
            compiled.append({
                "sceneId": scene_id,
                "start": float(scene.get("start") or 0),
                "end": float(scene.get("end") or 0),
                "text": str(scene.get("text") or scene.get("summary") or ""),
                "direction": str(scene.get("direction") or ""),
                "visualSpec": visual_spec,
            })
        return {"pack": normalized, "packFingerprint": normalized["fingerprint"], "scenePlan": {"version": 2, "packId": normalized["packId"], "packVersion": normalized["version"], "packFingerprint": normalized["fingerprint"], "scenes": compiled}, "warnings": checked["warnings"], "errors": []}


def render_eval_artifact(visual_spec: dict[str, Any], scene: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    """Run the existing renderer in an isolated directory and keep reproducible evidence."""
    from visual_assets.code_visual.motion_export import frame_svg, render_motion_mp4
    from visual_assets.contracts import RenderConfig, RoutingOptions, VisualAssetSourceItem, VisualSemantic
    from visual_assets.registry import get_provider

    output_dir.mkdir(parents=True, exist_ok=True)
    provider = get_provider(str(visual_spec["providerId"]))
    params = dict(visual_spec.get("parameters") or {})
    visual_family = str(params.get("visualFamily") or "evidence")
    duration = max(0.8, float(scene.get("end") or 3) - float(scene.get("start") or 0))
    item = VisualAssetSourceItem(
        id=str(visual_spec["sceneId"]), order=1, subtitleIds=[str(visual_spec["sceneId"])], start=0, end=duration,
        text=str(scene.get("text") or "Production Pack Eval"),
        semantic=VisualSemantic(topic="production-pack-eval", visualIntent=visual_family, metadata={"rendererId": visual_spec["rendererId"], "themeMode": visual_spec["themeMode"], "ipPack": str(params.get("ipPack") or "neutral"), "visualFamily": visual_family}),
    )
    route = provider.route(item, RoutingOptions())
    rendered = provider.render_svg(item, route, RenderConfig(provider=str(visual_spec["providerId"]), providerVersion=getattr(provider, "provider_version", "0"), providerOptions={"rendererId": visual_spec["rendererId"], "themeMode": visual_spec["themeMode"], "ipPack": str(params.get("ipPack") or "neutral")}))
    svg_path = output_dir / "artifact.svg"
    svg_path.write_text(rendered.svg, encoding="utf-8")
    motion = dict((rendered.motionHint or {}).get("motionPlan") or {})
    frame_path = output_dir / "representative-frame.svg"
    frame_path.write_text(frame_svg(rendered.svg, motion, min(0.4, float(motion.get("duration") or duration) * 0.4), width=1080, height=1920), encoding="utf-8")
    result = {
        "rendererId": visual_spec["rendererId"], "templateId": rendered.templateId, "svgPath": str(svg_path), "svgSha256": hashlib.sha256(svg_path.read_bytes()).hexdigest(),
        "representativeFramePath": str(frame_path), "representativeFrameSha256": hashlib.sha256(frame_path.read_bytes()).hexdigest(),
        "duration": float(motion.get("duration") or duration), "outputMode": visual_spec["outputMode"], "warnings": [],
    }
    if visual_spec["outputMode"] == "video":
        video_path = output_dir / "artifact.mp4"
        try:
            render_motion_mp4(svg_path, motion, video_path, width=1080, height=1920, fps=int(params.get("videoFps") or 12))
            result.update({"artifactPath": str(video_path), "artifactSha256": hashlib.sha256(video_path.read_bytes()).hexdigest(), "artifactType": "video", "byteSize": video_path.stat().st_size})
        except Exception as exc:
            result["warnings"].append(f"video_export_unavailable:{exc}")
            result.update({"artifactPath": str(svg_path), "artifactSha256": result["svgSha256"], "artifactType": "svg", "byteSize": svg_path.stat().st_size})
    else:
        result.update({"artifactPath": str(svg_path), "artifactSha256": result["svgSha256"], "artifactType": "svg", "byteSize": svg_path.stat().st_size})
    return result


def new_eval_run_id() -> str:
    return f"pack_eval_{uuid4().hex[:12]}"
