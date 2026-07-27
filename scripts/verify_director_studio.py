"""End-to-end deterministic verification for private Skills and Director Packs."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from agent.lab_runner.run_store import RunStore
from agent_runtime.director_service import DirectorService
from agent_runtime.director_store import DirectorStore
from agent_runtime.director_studio import DirectorStudioRegistry
from agent_runtime.pi_transport import FakePiTransport


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="videoforge-director-studio-") as temp:
        root = Path(temp)
        registry = DirectorStudioRegistry(root=root / "studio", recipes_root=ROOT / "agent" / "recipes")
        seed = registry.get_skill("subtitle_scene_director")
        assert seed["status"] == "published"

        draft = registry.import_gpt_draft("""我要做低饱和纪录片风格的知识视频。
字幕一句对应一个画面，不做花哨转场。重点观点用暖棕和金色信息卡。
优先使用真实素材；替换现有素材必须先问我。""")
        assert draft["status"] == "draft"
        assert registry.validate_skill(draft["skillId"])["ok"]
        trial = registry.trial_skill(draft["skillId"])
        assert len(trial["scenePlan"]["scenes"]) == 2
        published = registry.publish_skill(draft["skillId"])
        assert published["status"] == "published"

        revised = registry.update_skill(draft["skillId"], {"directives": {**published["directives"], "visualStyle": "黑白报纸拼贴与红色重点。"}})
        assert revised["version"] == 2 and revised["status"] == "draft"
        registry.publish_skill(draft["skillId"])
        assert registry.rollback_skill(draft["skillId"], 1)["version"] == 1

        subtitles = [
            {"id": "scene_alpha", "start": 0, "end": 2.5, "text": "先让观众看懂核心观点。"},
            {"id": "scene_beta", "start": 2.5, "end": 5.2, "text": "再用画面解释复杂关系。"},
        ]
        documentary = registry.save_pack({
            "name": "纪录片知识视频",
            "recipeId": "structured-knowledge-video",
            "skillPins": [{"skillId": "subtitle_scene_director", "version": 1}],
            "style": {"name": "纪录片", "palette": "暖棕与低饱和金色", "mood": "克制"},
            "capabilityIds": ["review_visual_scene_plan", "bind_scene_assets"],
        })
        collage = registry.save_pack({
            "name": "报纸拼贴知识视频",
            "recipeId": "structured-knowledge-video",
            "skillPins": [{"skillId": "subtitle_scene_director", "version": 1}],
            "style": {"name": "报纸拼贴", "palette": "黑白与红色", "mood": "锐利"},
            "capabilityIds": ["review_visual_scene_plan", "bind_scene_assets"],
        })
        first = registry.resolve_pack(documentary["packId"])
        second = registry.resolve_pack(collage["packId"])
        first_plan = registry.build_scene_plan(subtitles, first["skills"], first["pack"])
        second_plan = registry.build_scene_plan(subtitles, second["skills"], second["pack"])
        assert first_plan["styleSignature"] != second_plan["styleSignature"]
        assert first_plan["scenes"][0]["start"] == 0 and first_plan["scenes"][0]["end"] == 2.5

        document = registry.export_pack(documentary["packId"])
        imported_registry = DirectorStudioRegistry(root=root / "imported", recipes_root=ROOT / "agent" / "recipes")
        imported = imported_registry.import_pack(document)
        assert imported["imported"] is True
        imported_registry.uninstall_pack(imported["packId"])
        assert not imported_registry.list_packs()

        service = DirectorService(store=DirectorStore(RunStore(root / "runs")), transport=FakePiTransport())
        run = service.create_run({
            "task": "Apply the selected private Director Pack.",
            "recipeId": documentary["recipeId"],
            "directorPack": first["pack"],
            "skills": first["skills"],
            "scenePlan": first_plan,
            "intake": {"subtitleTimeline": subtitles},
        })
        assert run["directorPack"]["packId"] == documentary["packId"]
        assert run["scenePlan"]["styleSignature"] == first_plan["styleSignature"]
        assert any(event["type"] == "scene_plan.proposed" for event in service.events(run["runId"]))
        print({"skills": len(registry.list_skills()), "pack": documentary["packId"], "scenes": len(first_plan["scenes"]), "runId": run["runId"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
