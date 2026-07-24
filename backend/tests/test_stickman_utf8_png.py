import json
from pathlib import Path

from visual_assets.contracts import VisualAssetRenderRequest
from visual_assets.rasterizer import PillowSvgRasterizer, validate_png_alpha
from visual_assets.service import render_visual_asset_project


def test_utf8_cases_render_transparent_png_and_skip_unchanged(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "stickman_cases.json"
    raw = json.loads(fixture.read_text(encoding="utf-8"))
    request = VisualAssetRenderRequest.model_validate(raw)
    result = render_visual_asset_project(request, tmp_path, PillowSvgRasterizer())
    assert result.status == "succeeded"
    assert [item.templateId for item in result.items] == [
        "red_string_control",
        "burden_boulder",
        "inner_conflict",
    ]
    assert (tmp_path / "contact_sheet.svg").exists()
    assert (tmp_path / "contact_sheet.png").exists()
    for item in result.items:
        png = tmp_path / item.pngPath
        assert validate_png_alpha(png, 1080, 1920) == []
    repeated = render_visual_asset_project(request, tmp_path, PillowSvgRasterizer())
    assert [item.status for item in repeated.items] == ["skipped_unchanged"] * 3
