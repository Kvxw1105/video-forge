from visual_assets.contact_sheet import build_contact_sheet_svg
from visual_assets.contracts import VisualAssetManifest, VisualAssetRenderRequest
from visual_assets.service import render_visual_asset_project

from test_stickman_batch_service import request_data


def test_contact_sheet_uses_manifest_order(tmp_path):
    render_visual_asset_project(VisualAssetRenderRequest.model_validate(request_data()), tmp_path)
    manifest = VisualAssetManifest.model_validate_json((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    path = build_contact_sheet_svg(manifest, tmp_path / "contact_sheet_2.svg")
    text = path.read_text(encoding="utf-8")
    assert text.index("0001") < text.index("0002") < text.index("0003")
