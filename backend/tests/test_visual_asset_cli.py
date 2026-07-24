import json

from visual_assets.cli import main
from test_stickman_batch_service import request_data


def test_cli_list_templates_and_render(tmp_path, capsys):
    assert main(["list-templates"]) == 0
    assert "red_string_control" in capsys.readouterr().out
    inp = tmp_path / "segments.json"
    inp.write_text(json.dumps(request_data(), ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "out"
    assert main(["render", "--input", str(inp), "--output", str(out), "--svg", "--contact-sheet"]) == 0
    assert (out / "manifest.json").exists()
