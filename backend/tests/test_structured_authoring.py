import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import create_app
from services import project_service
from routers import structured_authoring
from agent_runtime.raw_script_organizer import OrganizerError
from shared.structured_import import detect_block_type, parse_structured_markdown
from shared.structured_presets import build_blocks, build_default_structured_variants


def test_parser_is_deterministic_and_preserves_paragraphs():
    source = "# Episode\n\n## hook:\n第一段。\n\n第二段。\n\n[故事]\n案例内容"
    first = parse_structured_markdown(source)
    second = parse_structured_markdown(source)
    assert first == second
    assert first.title == "Episode"
    assert first.sections[0].detected_type == "HOOK"
    assert first.sections[0].text == "第一段。\n\n第二段。"
    assert first.sections[1].detected_type == "STORY"


def test_parser_unknown_and_empty_sections_are_explicit():
    result = parse_structured_markdown("## 未知标题\n内容\n## STORY\n")
    assert result.sections[0].detected_type is None
    assert "unknown_section" in result.sections[0].warnings
    assert "empty_section" in result.sections[1].warnings


@pytest.mark.parametrize("source", [
    "preface without headings",
    "# Title\n\nintro before the first section\n\n## STORY\nbody",
    "intro before title\n\n# Title\n\nintro after title",
])
def test_parser_retains_unassigned_preamble(source):
    result = parse_structured_markdown(source)
    assert result.sections[0].source_heading == "PREAMBLE"
    assert result.sections[0].detected_type is None
    assert "unassigned_preamble" in result.sections[0].warnings


def test_new_chinese_aliases_are_detected():
    assert detect_block_type("艾特引导") == "CTA_TAG"
    assert detect_block_type("艺特引导") == "CTA_TAG"
    assert detect_block_type("破法") == "METHOD"
    assert detect_block_type("章节尾钩") == "BRIDGE_OUT"


def test_parser_rejects_empty_and_oversized_input():
    with pytest.raises(ValueError):
        parse_structured_markdown(" \n")
    with pytest.raises(ValueError):
        parse_structured_markdown("x" * 200_001)


def test_presets_keep_order_and_choose_fallback_active_variant():
    blocks = [{"id": "story_01", "type": "STORY", "text": "x"}, {"id": "bridge_in_01", "type": "BRIDGE_IN", "text": "y"}]
    result = build_default_structured_variants(blocks)
    assert result["activeVariantId"] == "publish"
    assert result["variants"][0]["blockIds"] == ["story_01"]
    assert result["variants"][2]["blockIds"] == ["story_01", "bridge_in_01"]


def _client(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    return TestClient(create_app())


def test_import_api_recognizes_canonical_ait_alias(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/structured/import/parse",
        json={"text": "## 艾特引导\n把这条内容艾特给真正需要的人。"},
    )
    assert response.status_code == 200
    assert response.json()["sections"][0]["detectedType"] == "CTA_TAG"


def _episode():
    blocks = [{"id": "story_01", "type": "STORY", "text": "故事"}]
    return {"episodeId": "ep_01", "title": "标题", "topic": "主题", "symbol": "#", "blocks": blocks, "variants": [{"id": "publish", "name": "Publish", "blockIds": ["story_01"]}], "activeVariantId": "publish"}


def test_structured_create_parse_and_safe_draft_update(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    parsed = client.post("/api/structured/import/parse", json={"text": "# T\n## STORY\n正文"})
    assert parsed.status_code == 200
    created = client.post("/api/projects/structured", json={"name": "structured", "episode": _episode(), "canvas": {"ratio": "9:16"}})
    assert created.status_code == 200
    body = created.json()
    assert body["templateId"] == "structured_episode"
    assert body["script"] == "故事"
    assert body["assets"] == [] and body["subtitles"] == [] and body["audio"]["voiceovers"] == []
    project_id = body["id"]
    updated = client.patch(f"/api/projects/{project_id}/structured/draft", json={"expectedUpdatedAt": body["updated_at"], "title": "新标题"})
    assert updated.status_code == 200
    conflict = client.patch(f"/api/projects/{project_id}/structured/draft", json={"expectedUpdatedAt": body["updated_at"], "title": "过期"})
    assert conflict.status_code == 200 and conflict.json()["status"] == "conflict"


def test_structured_draft_update_rejects_existing_audio_slice(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    episode = _episode()
    episode["bindings"] = [{"blockId": "story_01", "audioSlice": {"voiceoverId": "vo", "sourceStart": 0, "sourceEnd": 1}}]
    created = client.post("/api/projects/structured", json={"name": "structured", "episode": episode})
    assert created.status_code == 200
    response = client.patch(f"/api/projects/{created.json()['id']}/structured/draft", json={"title": "blocked"})
    assert response.status_code == 409
    assert response.json()["detail"] == "structured_alignment_exists"


@pytest.mark.parametrize("episode", [
    {"episodeId": "ep", "blocks": [], "variants": [], "activeVariantId": None},
    {"episodeId": "ep", "blocks": [{"id": "story", "type": "STORY", "text": "text"}], "variants": [], "activeVariantId": None},
    {"episodeId": "ep", "blocks": [{"id": "story", "type": "STORY", "text": "text"}], "variants": [{"id": "publish", "name": "Publish", "blockIds": []}], "activeVariantId": "publish"},
    {"episodeId": "ep", "blocks": [{"id": "story", "type": "STORY", "text": ""}], "variants": [{"id": "publish", "name": "Publish", "blockIds": ["story"]}], "activeVariantId": "publish"},
])
def test_structured_create_rejects_incomplete_authoring_payload(monkeypatch, tmp_path, episode):
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/projects/structured", json={"name": "invalid", "episode": episode})
    assert response.status_code == 422
    assert list(tmp_path.iterdir()) == []


def test_raw_txt_agent_organizes_without_creating_project_until_confirmed(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(structured_authoring, "organize_source", lambda text: {
        "title": "情绪的代价", "summary": "拆成问题、机制和方法。", "warnings": [],
        "blocks": [
            {"id": "hook_01", "type": "HOOK", "text": "你以为忍住就是成熟。", "enabled": True, "revision": 1, "metadata": {"semantic": {"visualIntent": "hook"}, "confidence": 0.93}, "warnings": []},
            {"id": "mechanism_01", "type": "MECHANISM", "text": "压抑会把感受推迟到账。", "enabled": True, "revision": 1, "metadata": {"semantic": {"visualIntent": "explain"}, "confidence": 0.88}, "warnings": []},
            {"id": "method_01", "type": "METHOD", "text": "先给感受命名，再决定行动。", "enabled": True, "revision": 1, "metadata": {"semantic": {"visualIntent": "method"}, "confidence": 0.81}, "warnings": []},
        ],
    })
    response = client.post("/api/structured/import/organize", json={"text": "你以为忍住就是成熟。压抑会把感受推迟到账。先给感受命名。"})
    assert response.status_code == 200
    assert [block["type"] for block in response.json()["blocks"]] == ["HOOK", "MECHANISM", "METHOD"]
    assert list(tmp_path.iterdir()) == []
    created = client.post("/api/projects/structured", json={"name": "情绪的代价", "episode": {"episodeId": "ep_raw", "title": "情绪的代价", "blocks": response.json()["blocks"], "variants": [{"id": "publish", "name": "Publish", "blockIds": ["hook_01", "mechanism_01", "method_01"]}], "activeVariantId": "publish"}})
    assert created.status_code == 200


def test_raw_markdown_agent_keeps_title_and_body(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    source = "# 不必讨好所有人\n\n有些关系让你一直解释自己。\n\n真正的边界，是允许别人失望。"
    monkeypatch.setattr(structured_authoring, "organize_source", lambda text: {"title": "不必讨好所有人", "summary": "保留标题和正文。", "warnings": [], "blocks": [{"id": "problem_01", "type": "PROBLEM", "text": "有些关系让你一直解释自己。", "enabled": True, "revision": 1, "metadata": {"semantic": {}, "confidence": 0.8}, "warnings": []}, {"id": "judgment_01", "type": "JUDGMENT", "text": "真正的边界，是允许别人失望。", "enabled": True, "revision": 1, "metadata": {"semantic": {}, "confidence": 0.8}, "warnings": []}]})
    response = client.post("/api/structured/import/organize", json={"text": source})
    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "不必讨好所有人"
    assert "解释自己" in payload["blocks"][0]["text"]
    assert "允许别人失望" in payload["blocks"][1]["text"]


def test_raw_agent_failure_returns_clear_degradation_without_project(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(structured_authoring, "organize_source", lambda text: (_ for _ in ()).throw(OrganizerError("Agent 模型服务尚未配置。请先在 Agent 设置中保存并测试连接，或使用手动分段。")))
    response = client.post("/api/structured/import/organize", json={"text": "这是一段原文。"})
    assert response.status_code == 409
    assert "手动分段" in response.json()["detail"]
    assert list(tmp_path.iterdir()) == []
