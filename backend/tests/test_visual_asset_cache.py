from visual_assets.cache import atomic_write_json, atomic_write_text, read_json


def test_atomic_writes_and_json_recovery(tmp_path):
    path = tmp_path / "x.json"
    atomic_write_json(path, {"b": 1})
    assert read_json(path) == {"b": 1}
    atomic_write_text(path, "{")
    assert read_json(path) is None
