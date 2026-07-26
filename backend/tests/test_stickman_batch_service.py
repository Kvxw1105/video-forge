import json

from visual_assets.contracts import VisualAssetRenderRequest
from visual_assets.service import render_visual_asset_project


def request_data():
    return {
        "schemaVersion": 1,
        "projectId": "proj_demo",
        "source": {"mode": "inline_segments", "segments": [
            {"id": "scene_a", "order": 1, "blockId": "b1", "subtitleIds": ["s1"], "start": 0, "end": 2, "text": "越害怕失去的人，越容易提前控制关系。", "semantic": {"actors": 2, "visualIntent": "red_string_pull"}},
            {"id": "scene_b", "order": 2, "blockId": "b2", "subtitleIds": ["s2"], "start": 2, "end": 4, "text": "他背着整个家族的期待，却没有人问过他累不累。", "semantic": {"actors": 1}},
            {"id": "scene_c", "order": 3, "blockId": "b3", "subtitleIds": ["s3"], "start": 4, "end": 6, "text": "一个自己想逃走，另一个自己逼着他继续证明。", "semantic": {"actors": 2}},
        ]},
        "exports": {"svg": True, "png": False, "manifest": True, "contactSheet": True, "generationReport": True},
    }


def test_batch_generation_manifest_contact_sheet_and_cache(tmp_path):
    req = VisualAssetRenderRequest.model_validate(request_data())
    first = render_visual_asset_project(req, tmp_path)
    assert first.status == "succeeded"
    assert [item.templateId for item in first.items] == ["red_string_control", "burden_boulder", "inner_conflict"]
    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "contact_sheet.svg").exists()
    second = render_visual_asset_project(req, tmp_path)
    assert all(item.status == "skipped_unchanged" for item in second.items)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert [item["order"] for item in manifest["items"]] == [1, 2, 3]


def test_manual_override_protection(tmp_path):
    req = VisualAssetRenderRequest.model_validate(request_data())
    render_visual_asset_project(req, tmp_path)
    svg = next((tmp_path / "assets").glob("0001_*.svg"))
    svg.write_text(svg.read_text(encoding="utf-8") + "\n<!-- manual -->", encoding="utf-8")
    result = render_visual_asset_project(req, tmp_path)
    assert result.items[0].status == "manual_override"


def test_single_segment_regenerate_preserves_other_items(tmp_path):
    data = request_data()
    render_visual_asset_project(VisualAssetRenderRequest.model_validate(data), tmp_path)
    data["behavior"] = {"existingOutputPolicy": "regenerate", "replaceManualEdits": True, "segmentId": "scene_b"}
    result = render_visual_asset_project(VisualAssetRenderRequest.model_validate(data), tmp_path)
    assert [item.segmentId for item in result.items] == ["scene_a", "scene_b", "scene_c"]
