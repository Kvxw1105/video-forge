from visual_assets.contracts import VisualAssetManifest

from test_stickman_batch_service import request_data
from visual_assets.contracts import VisualAssetRenderRequest
from visual_assets.service import render_visual_asset_project


def test_manifest_contract_round_trip(tmp_path):
    render_visual_asset_project(VisualAssetRenderRequest.model_validate(request_data()), tmp_path)
    manifest = VisualAssetManifest.model_validate_json((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.items[0].svgSha256
    assert manifest.items[0].duration == 2
