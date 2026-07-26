import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.structured_content import compile_structured_media_variant
from shared.visual_scene import build_narration_units, propose_scenes, validate_plan, visual_source_hash


def _project(tmp_path):
    voice = tmp_path / "voice.wav"; voice.write_bytes(b"wav")
    image = tmp_path / "image.png"; image.write_bytes(b"png")
    video = tmp_path / "video.mp4"; video.write_bytes(b"mp4")
    value = {"id":"p","name":"P","assets":[{"id":"img","type":"image","name":"image.png","path":str(image),"metadata":{}},{"id":"vid","type":"video","name":"video.mp4","path":str(video),"metadata":{}}],"audio":{"voiceover":{},"voiceovers":[{"id":"vo","file":str(voice),"duration":15,"isActive":False}],"bgm":{"tracks":[]},"sfx":[]},"subtitles":[{"id":f"s{i}","text":f"line {i}{'。' if i in {3,6} else ''}","start":float(i-1),"end":float(i),"style":{},"metadata":{}} for i in range(1,7)],"structuredContent":{"schemaVersion":1,"episode":{"episodeId":"ep","blocks":[{"id":"a","type":"STORY","text":"A"},{"id":"b","type":"METHOD","text":"B"}],"variants":[{"id":"publish","name":"Publish","blockIds":["a","b"]},{"id":"master","name":"Master","blockIds":["b","a"]}],"activeVariantId":"publish","bindings":[{"blockId":"a","audioSlice":{"voiceoverId":"vo","sourceStart":0,"sourceEnd":3},"visualAssetIds":["img"],"subtitleIds":["s1","s2","s3"]},{"blockId":"b","audioSlice":{"voiceoverId":"vo","sourceStart":3,"sourceEnd":6},"visualAssetIds":["vid"],"subtitleIds":["s4","s5","s6"]}]}}}
    return value


def test_narration_units_restore_multiple_subtitles(tmp_path):
    project = _project(tmp_path)
    units = build_narration_units(project["subtitles"][:3])
    assert len(units) == 1 and units[0].subtitle_ids == ("s1", "s2", "s3")


def test_visual_plan_validation_and_variant_relative_timing(tmp_path):
    project = _project(tmp_path); source_hash = visual_source_hash(project)
    plan = {"schemaVersion":1,"planId":"plan_1","sourceHash":source_hash,"scenes":[{"id":"scene_a","blockId":"a","subtitleIds":["s1","s2","s3"],"visualAssetIds":["img"],"requestedMediaType":"image"},{"id":"scene_b","blockId":"b","subtitleIds":["s4","s5","s6"],"visualAssetIds":["vid"],"requestedMediaType":"video"}],"settings":{}}
    assert validate_plan(project, plan) == []
    project["structuredContent"]["episode"]["visualPlan"] = plan
    publish = compile_structured_media_variant(project,"publish",duration_resolver=lambda _: 6)
    master = compile_structured_media_variant(project,"master",duration_resolver=lambda _: 6)
    assert [(item["start"],item["end"]) for item in publish.project_view["segments"]] == [(0.0,3.0),(3.0,6.0)]
    assert [(item["start"],item["end"]) for item in master.project_view["segments"]] == [(0.0,3.0),(3.0,6.0)]
    assert [item["metadata"]["sceneId"] for item in master.project_view["segments"]] == ["scene_b","scene_a"]


def test_visual_plan_rejects_cross_block_overlap_and_stale(tmp_path):
    project = _project(tmp_path)
    bad = {"sourceHash":"x" * 64,"scenes":[{"id":"bad","blockId":"a","subtitleIds":["s1","s4"]}]}
    errors = validate_plan(project,bad)
    assert any("crosses block" in error for error in errors) and any("stale" in error for error in errors)


def test_proposal_fixed_units_keeps_block_boundaries(tmp_path):
    project = _project(tmp_path)
    scenes = propose_scenes(project,{"mode":"fixed_units","unitsPerScene":1})
    assert [scene["blockId"] for scene in scenes] == ["a","b"]


def test_block_presentation_controls_granularity_metadata_and_source_hash(tmp_path):
    project = _project(tmp_path)
    for subtitle in project["subtitles"]:
        subtitle["text"] += "!"
    blocks = project["structuredContent"]["episode"]["blocks"]
    before = visual_source_hash(project)
    blocks[0]["metadata"] = {"presentation": {
        "templateId": "story_gallery",
        "granularity": "coarse",
        "providerPreferences": ["ai_image", "stock_video"],
    }}
    blocks[1]["metadata"] = {"presentation": {
        "templateId": "mechanism_explainer",
        "granularity": "fine",
        "visualPolicy": {"providerPreferences": ["code_visual_svg"]},
    }}

    scenes = propose_scenes(project, {"mode": "fixed_units", "unitsPerScene": 2})
    coarse = [scene for scene in scenes if scene["blockId"] == "a"]
    fine = [scene for scene in scenes if scene["blockId"] == "b"]

    assert len(coarse) == 1
    assert len(fine) == 3
    assert coarse[0]["metadata"] == {
        "presentationTemplateId": "story_gallery",
        "granularity": "coarse",
        "providerPreferences": ["ai_image", "stock_video"],
        "visualPolicy": {"mode": "hybrid", "targetDuration": 12, "minDuration": 5, "maxDuration": 18, "unitsPerScene": 2},
    }
    assert fine[0]["metadata"]["presentationTemplateId"] == "mechanism_explainer"
    assert fine[0]["metadata"]["providerPreferences"] == ["code_visual_svg"]
    assert visual_source_hash(project) != before
    plan = {"sourceHash": visual_source_hash(project), "scenes": scenes}
    assert validate_plan(project, plan) == []
    assert {sid for scene in scenes for sid in scene["subtitleIds"]} == {"s1", "s2", "s3", "s4", "s5", "s6"}


def test_custom_block_presentation_uses_its_own_sentence_grouping(tmp_path):
    project = _project(tmp_path)
    for subtitle in project["subtitles"]:
        subtitle["text"] = f"{subtitle['text'].rstrip('。')}。"
    block = project["structuredContent"]["episode"]["blocks"][0]
    block["metadata"] = {"presentation": {
        "templateId": "story_sequence",
        "presentationStyle": "narrative_sequence",
        "granularity": "custom",
        "providerPreferences": ["ai_image"],
        "visualPolicy": {"mode": "fixed_units", "unitsPerScene": 2, "targetDuration": 9},
    }}
    scenes = propose_scenes(project, {"mode": "fixed_units", "unitsPerScene": 1})
    block_scenes = [scene for scene in scenes if scene["blockId"] == "a"]
    assert len(block_scenes) == 2
    assert block_scenes[0]["subtitleIds"] == ["s1", "s2"]
    assert block_scenes[0]["metadata"] == {
        "presentationTemplateId": "story_sequence",
        "presentationStyle": "narrative_sequence",
        "granularity": "custom",
        "providerPreferences": ["ai_image"],
        "visualPolicy": {"mode": "fixed_units", "unitsPerScene": 2, "targetDuration": 9},
    }


def test_fifteen_subtitles_three_scenes_cover_without_gaps(tmp_path):
    project = _project(tmp_path)
    project["subtitles"] = [{"id": f"s{i:02d}", "text": f"line {i}", "start": float(i - 1), "end": float(i), "style": {}, "metadata": {}} for i in range(1, 16)]
    project["structuredContent"]["episode"]["blocks"] = [{"id": "a", "type": "STORY", "text": "A"}, {"id": "b", "type": "METHOD", "text": "B"}, {"id": "c", "type": "JUDGMENT", "text": "C"}]
    project["structuredContent"]["episode"]["variants"] = [{"id":"publish","name":"Publish","blockIds":["a","b","c"]},{"id":"master","name":"Master","blockIds":["c","a"]}]
    project["structuredContent"]["episode"]["bindings"] = [{"blockId": block, "audioSlice":{"voiceoverId":"vo","sourceStart": index * 5,"sourceEnd":(index + 1) * 5}, "subtitleIds":[f"s{i:02d}" for i in range(index * 5 + 1,index * 5 + 6)]} for index, block in enumerate(["a","b","c"])]
    plan = {"schemaVersion":1,"planId":"plan_15","sourceHash":visual_source_hash(project),"scenes":[{"id":"scene_a","blockId":"a","subtitleIds":[f"s{i:02d}" for i in range(1,6)],"visualAssetIds":["img"]},{"id":"scene_b","blockId":"b","subtitleIds":[f"s{i:02d}" for i in range(6,11)],"visualAssetIds":["vid"]},{"id":"scene_c","blockId":"c","subtitleIds":[f"s{i:02d}" for i in range(11,16)],"visualAssetIds":["img"]}],"settings":{}}
    project["structuredContent"]["episode"]["visualPlan"] = plan
    publish=compile_structured_media_variant(project,"publish",duration_resolver=lambda _:15)
    assert len(publish.project_view["subtitles"]) == 15
    assert [(item["start"],item["end"]) for item in publish.project_view["segments"]] == [(0.0,5.0),(5.0,10.0),(10.0,15.0)]
    assert [item["type"] for item in publish.project_view["segments"]] == ["image","video","image"]
    master=compile_structured_media_variant(project,"master",duration_resolver=lambda _:15)
    assert [item["metadata"]["sceneId"] for item in master.project_view["segments"]] == ["scene_c","scene_a"]
