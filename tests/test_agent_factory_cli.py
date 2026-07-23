import json
from vforge import cli, client

def test_factory_cli_pending_outputs_json(monkeypatch,capsys):
    monkeypatch.setattr(client,"factory_pending_visuals",lambda batch,base:{"batchId":batch,"items":[]})
    cli.main(["factory-pending-visuals","--batch-id","b"])
    assert json.loads(capsys.readouterr().out)["batchId"]=="b"
