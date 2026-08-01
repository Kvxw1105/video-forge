"""Fast contract verification for executable Production Pack V2 manifests."""
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from agent_runtime.production_packs import ProductionPackCompiler, builtin_packs, migrate_v1_pack


FAMILIES = ("control", "anxiety", "people_pleasing", "evidence", "awakening", "hidden_path", "trap_detection")
CAPABILITIES = {"review_visual_scene_plan", "prepare_visual_generation_pack", "bind_scene_assets"}


def registry() -> dict:
    rows = []
    for renderer_id in ("mechanism_diagram", "pixel_rules", "white_sketch", "silhouette"):
        rows.append({
            "providerId": "code_visual_svg", "rendererId": renderer_id,
            "templateIds": [f"{renderer_id}:{family}" for family in FAMILIES],
            "supportedOutputModes": ["svg", "png", "video", "transparent_sequence"],
            "supportedPresentationModes": ["main", "overlay"],
            "supportedThemeModes": ["light", "dark"],
            "availability": "available", "missingDependencies": [],
        })
    return {"renderers": rows}


def published(_: str, __: int) -> dict:
    return {"status": "published"}


def expect_rejected(compiler: ProductionPackCompiler, pack: dict, code: str) -> None:
    result = compiler.validate(pack, capabilities=CAPABILITIES, skill_lookup=published)
    codes = {item["code"] for item in result["errors"]}
    assert code in codes, (code, codes)


def main() -> None:
    compiler = ProductionPackCompiler(registry)
    knowledge = builtin_packs()["knowledge-structure-motion"]
    editorial = builtin_packs()["minimal-editorial"]
    assert compiler.validate(knowledge, capabilities=CAPABILITIES, skill_lookup=published, require_eval_cases=True)["ok"]
    assert compiler.validate(editorial, capabilities=CAPABILITIES, skill_lookup=published, require_eval_cases=True)["ok"]

    legacy, warnings = migrate_v1_pack({
        "schemaVersion": 1, "packId": "legacy-documentary", "name": "旧版导演包", "recipeId": "structured-knowledge-video",
        "skillPins": [{"skillId": "subtitle_scene_director", "version": 1}], "style": {"name": "纪录片", "palette": "暖棕"},
        "templates": ["mechanism_diagram"], "capabilityIds": list(CAPABILITIES),
    })
    assert legacy["schemaVersion"] == 2 and warnings
    assert compiler.validate(legacy, capabilities=CAPABILITIES, skill_lookup=published)["ok"]

    semantic_cases = {
        "causal-mechanism": "因为外部评价进入自我判断，导致长期内耗。",
        "comparative-judgment": "两类人的区别在于是否把评价拆成事实。",
        "timeline-process": "第一步记录评价，然后区分解释，最后形成行动。",
        "hierarchy-network": "一个体系由中心、分支、关系网络组成。",
    }
    for expected, text in semantic_cases.items():
        scene = {"sceneId": "scene_001", "start": 0, "end": 3, "text": text}
        compiled = compiler.compile(knowledge, [scene], capabilities=CAPABILITIES, skill_lookup=published)
        spec = compiled["scenePlan"]["scenes"][0]["visualSpec"]
        assert spec["archetypeId"] == expected, (expected, spec)
        assert spec["selectionEvidence"]["source"] == "deterministic_pack_compiler"

    source = [{"sceneId": "scene_001", "start": 0, "end": 3, "text": "因为比较导致内耗。"}]
    first = compiler.compile(knowledge, source, capabilities=CAPABILITIES, skill_lookup=published)
    second = compiler.compile(knowledge, source, capabilities=CAPABILITIES, skill_lookup=published)
    comparison = compiler.compile(editorial, source, capabilities=CAPABILITIES, skill_lookup=published)
    assert first["packFingerprint"] == second["packFingerprint"]
    assert first["scenePlan"]["scenes"][0]["visualSpec"] == second["scenePlan"]["scenes"][0]["visualSpec"]
    assert first["scenePlan"]["scenes"][0]["visualSpec"]["rendererId"] != comparison["scenePlan"]["scenes"][0]["visualSpec"]["rendererId"]

    invalid_renderer = deepcopy(knowledge); invalid_renderer["rendererBindings"][0]["rendererId"] = "invented_renderer"
    expect_rejected(compiler, invalid_renderer, "renderer_not_registered")
    invalid_mode = deepcopy(knowledge); invalid_mode["rendererBindings"][0]["outputMode"] = "binary"
    expect_rejected(compiler, invalid_mode, "output_mode_unsupported")
    missing_binding = deepcopy(knowledge); missing_binding["sceneArchetypes"][0]["rendererBindingId"] = "missing"
    expect_rejected(compiler, missing_binding, "binding_missing")
    cycle = deepcopy(knowledge); cycle["sceneArchetypes"][0]["fallbackArchetypeId"] = "comparative-judgment"; cycle["sceneArchetypes"][1]["fallbackArchetypeId"] = "causal-mechanism"
    expect_rejected(compiler, cycle, "fallback_cycle")
    unsafe = deepcopy(knowledge); unsafe["providerPolicy"]["command"] = "echo insecure"
    result = compiler.validate(unsafe, capabilities=CAPABILITIES, skill_lookup=published)
    assert result["errors"][0]["code"] == "unsafe_executable_field", result
    print("verify_production_packs: ok")


if __name__ == "__main__":
    main()
