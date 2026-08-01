"""Focused contract tests for the executable Production Pack V2 compiler."""
from __future__ import annotations

from copy import deepcopy

from agent_runtime.production_packs import ProductionPackCompiler, builtin_packs, migrate_v1_pack


FAMILIES = ("control", "anxiety", "people_pleasing", "evidence", "awakening", "hidden_path", "trap_detection")
CAPABILITIES = {"review_visual_scene_plan", "prepare_visual_generation_pack", "bind_scene_assets"}


def _registry() -> dict:
    return {
        "renderers": [
            {
                "providerId": "code_visual_svg",
                "rendererId": renderer_id,
                "templateIds": [f"{renderer_id}:{family}" for family in FAMILIES],
                "supportedOutputModes": ["svg", "png", "video", "transparent_sequence"],
                "supportedPresentationModes": ["main", "overlay"],
                "supportedThemeModes": ["light", "dark"],
                "availability": "available",
                "missingDependencies": [],
            }
            for renderer_id in ("mechanism_diagram", "pixel_rules", "white_sketch", "silhouette")
        ]
    }


def _published(_: str, __: int) -> dict:
    return {"status": "published"}


def _compiler() -> ProductionPackCompiler:
    return ProductionPackCompiler(_registry)


def _error_codes(result: dict) -> set[str]:
    return {item["code"] for item in result["errors"]}


def test_v1_pack_normalizes_without_mutating_source() -> None:
    source = {
        "schemaVersion": 1,
        "packId": "legacy-documentary",
        "name": "旧版导演包",
        "recipeId": "structured-knowledge-video",
        "style": {"name": "纪录片", "palette": "暖棕"},
        "templates": ["mechanism_diagram"],
        "skillPins": [{"skillId": "subtitle_scene_director", "version": 1}],
        "capabilityIds": sorted(CAPABILITIES),
        "migration": {"sourceFormat": "videoforge-director-pack", "warnings": ["imported"]},
    }
    upgraded, warnings = migrate_v1_pack(source)
    assert source["schemaVersion"] == 1
    assert upgraded["schemaVersion"] == 2
    assert warnings and upgraded["rendererBindings"] and upgraded["sceneArchetypes"]
    assert upgraded["migration"]["sourceFormat"] == "videoforge-director-pack"
    assert _compiler().validate(upgraded, capabilities=CAPABILITIES, skill_lookup=_published)["ok"]


def test_visual_spec_is_deterministic_and_pack_specific() -> None:
    compiler = _compiler()
    packs = builtin_packs()
    source = [{"sceneId": "scene_001", "start": 0, "end": 3, "text": "因为比较导致内耗。"}]
    knowledge_a = compiler.compile(packs["knowledge-structure-motion"], source, capabilities=CAPABILITIES, skill_lookup=_published)
    knowledge_b = compiler.compile(packs["knowledge-structure-motion"], source, capabilities=CAPABILITIES, skill_lookup=_published)
    editorial = compiler.compile(packs["minimal-editorial"], source, capabilities=CAPABILITIES, skill_lookup=_published)
    assert knowledge_a["packFingerprint"] == knowledge_b["packFingerprint"]
    assert knowledge_a["scenePlan"]["scenes"][0]["visualSpec"] == knowledge_b["scenePlan"]["scenes"][0]["visualSpec"]
    assert knowledge_a["scenePlan"]["scenes"][0]["visualSpec"]["rendererId"] != editorial["scenePlan"]["scenes"][0]["visualSpec"]["rendererId"]


def test_semantic_selection_and_eval_matrix() -> None:
    compiler = _compiler()
    pack = builtin_packs()["knowledge-structure-motion"]
    examples = {
        "causal-mechanism": "因为外部评价进入自我判断，导致长期内耗。",
        "comparative-judgment": "两类人的区别在于是否把评价拆成事实。",
        "timeline-process": "第一步记录评价，然后区分解释，最后形成行动。",
        "hierarchy-network": "一个体系由中心、分支、关系网络组成。",
    }
    for expected, text in examples.items():
        compiled = compiler.compile(pack, [{"sceneId": "scene_001", "start": 0, "end": 3, "text": text}], capabilities=CAPABILITIES, skill_lookup=_published)
        assert compiled["scenePlan"]["scenes"][0]["visualSpec"]["archetypeId"] == expected
    case_ids = {item["caseId"] for item in pack["evalCases"]}
    assert {"abstract-view", "causal-explanation", "comparison", "process", "network", "long-text-pressure", "short-text"}.issubset(case_ids)
    assert {item["ratio"] for item in pack["evalCases"]} == {"9:16", "16:9"}


def test_invalid_runtime_contracts_are_rejected() -> None:
    compiler = _compiler()
    pack = builtin_packs()["knowledge-structure-motion"]
    invalid_renderer = deepcopy(pack); invalid_renderer["rendererBindings"][0]["rendererId"] = "invented_renderer"
    assert "renderer_not_registered" in _error_codes(compiler.validate(invalid_renderer, capabilities=CAPABILITIES, skill_lookup=_published))
    invalid_mode = deepcopy(pack); invalid_mode["rendererBindings"][0]["outputMode"] = "binary"
    assert "output_mode_unsupported" in _error_codes(compiler.validate(invalid_mode, capabilities=CAPABILITIES, skill_lookup=_published))
    missing_binding = deepcopy(pack); missing_binding["sceneArchetypes"][0]["rendererBindingId"] = "missing"
    assert "binding_missing" in _error_codes(compiler.validate(missing_binding, capabilities=CAPABILITIES, skill_lookup=_published))
    cycle = deepcopy(pack); cycle["sceneArchetypes"][0]["fallbackArchetypeId"] = "comparative-judgment"; cycle["sceneArchetypes"][1]["fallbackArchetypeId"] = "causal-mechanism"
    assert "fallback_cycle" in _error_codes(compiler.validate(cycle, capabilities=CAPABILITIES, skill_lookup=_published))
    unsafe = deepcopy(pack); unsafe["providerPolicy"]["command"] = "echo insecure"
    assert "unsafe_executable_field" in _error_codes(compiler.validate(unsafe, capabilities=CAPABILITIES, skill_lookup=_published))
    draft_skill = compiler.validate(pack, capabilities=CAPABILITIES, skill_lookup=lambda _id, _version: {"status": "draft"})
    assert "skill_not_published" in _error_codes(draft_skill)
