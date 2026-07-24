from visual_assets.contracts import VisualAssetRenderRequest
from visual_assets.hashing import hash_payload, input_hash_payload
from visual_assets.registry import get_provider

from test_visual_asset_contracts import base_request


def test_canonical_hash_stable_and_sorted():
    assert hash_payload({"b": 1.0, "a": [2, 3]}) == hash_payload({"a": [2.0, 3.0], "b": 1})


def test_input_hash_excludes_output_path():
    req = VisualAssetRenderRequest.model_validate(base_request())
    item = req.source.segments[0]
    provider = get_provider(req.renderer.provider)
    route = provider.route(item, req.routing)
    payload = input_hash_payload(item, route, req.renderer, req.exports)
    assert "output" not in str(payload).lower()
    assert hash_payload(payload) == hash_payload(payload)
