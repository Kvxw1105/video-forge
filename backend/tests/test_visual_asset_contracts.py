import pytest
from pydantic import ValidationError

from visual_assets.contracts import VisualAssetRenderRequest


def base_request():
    return {
        "schemaVersion": 1,
        "projectId": "proj_demo",
        "source": {"mode": "inline_segments", "segments": [{"id": "scene_001", "order": 1, "start": 0, "end": 2.8, "text": "控制关系", "semantic": {"actors": 2, "visualIntent": "red_string_pull"}}]},
    }


def test_valid_request_contract():
    req = VisualAssetRenderRequest.model_validate(base_request())
    assert req.source.segments[0].semantic.actors == 2
    assert req.renderer.provider == "stickman_svg"


@pytest.mark.parametrize("patch", [
    {"source": {"segments": [{"id": "scene_001", "order": 1, "start": 1, "end": 1, "text": "x"}]}},
    {"source": {"segments": [{"id": "scene_001", "order": 1, "start": -1, "end": 1, "text": "x"}]}},
    {"source": {"segments": [{"id": "scene_001", "order": 1, "start": 0, "end": 1, "text": ""}]}},
    {"source": {"segments": [{"id": "scene_001", "order": 1, "start": 0, "end": 1, "text": "x", "semantic": {"actors": 9}}]}},
    {"renderer": {"canvas": {"width": 20, "height": 1920}}},
    {"renderer": {"theme": {"foreground": "white"}}},
    {"routing": {"minimumConfidence": 2}},
])
def test_invalid_contract_values(patch):
    data = base_request()
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key].update(value)
        else:
            data[key] = value
    with pytest.raises(ValidationError):
        VisualAssetRenderRequest.model_validate(data)


def test_rejects_unknown_field_and_duplicate_ids():
    data = base_request()
    data["unknown"] = True
    with pytest.raises(ValidationError):
        VisualAssetRenderRequest.model_validate(data)
    data = base_request()
    data["source"]["segments"].append({**data["source"]["segments"][0], "order": 2})
    with pytest.raises(ValidationError):
        VisualAssetRenderRequest.model_validate(data)
