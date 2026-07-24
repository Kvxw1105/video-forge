from visual_assets.naming import asset_filename, slugify


def test_slugify_and_filename_are_stable():
    assert slugify("Scene_Mechanism 01/001") == "scene-mechanism-01-001"
    assert asset_filename(1, "Scene_Mechanism 01/001", "red_string_control", "svg") == "0001_scene-mechanism-01-001_red-string-control.svg"
    assert len(asset_filename(1, "x" * 300, "red_string_control", "svg")) <= 160
