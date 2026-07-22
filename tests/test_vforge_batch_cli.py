import json

from vforge import cli, client


def test_create_forwards_template_id(monkeypatch):
    captured = {}
    monkeypatch.setattr(client, "_request", lambda *args, **kwargs: captured.update(kwargs.get("json_body") or {}) or {"id": "p"})
    assert client.create_project("name", template_id="tpl_single_voiceover") == {"id": "p"}
    assert captured["template_id"] == "tpl_single_voiceover"


def test_batch_cli_plan_reads_at_file(monkeypatch, tmp_path, capsys):
    spec = tmp_path / "batch.json"; spec.write_text(json.dumps({"schemaVersion": 1}), encoding="utf-8")
    monkeypatch.setattr(client, "plan_template_batch", lambda value, base: {"specHash": "h", "valid": True})
    cli.main(["batch-plan", "--spec", f"@{spec}"])
    assert json.loads(capsys.readouterr().out)["specHash"] == "h"
