import json

from vforge import cli, client


def test_image_batch_cli_create_pending_and_status(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        client,
        "create_image_generation_batch",
        lambda pid, data, base: calls.append(("create", pid, data, base)) or {"batchId": "b1"},
    )
    monkeypatch.setattr(
        client,
        "get_pending_image_generation_requests",
        lambda pid, batch, base: calls.append(("pending", pid, batch, base)) or {"items": []},
    )
    monkeypatch.setattr(
        client,
        "get_image_generation_batch",
        lambda pid, batch, base: calls.append(("status", pid, batch, base)) or {"status": "awaiting_agent"},
    )

    cli.main(["image-batch-create", "--pid", "p1", "--data", '{"channel":"agent"}'])
    assert json.loads(capsys.readouterr().out)["batchId"] == "b1"
    cli.main(["image-batch-pending", "--pid", "p1", "--batch", "b1"])
    assert json.loads(capsys.readouterr().out)["items"] == []
    cli.main(["image-batch-status", "--pid", "p1", "--batch", "b1"])
    assert json.loads(capsys.readouterr().out)["status"] == "awaiting_agent"
    assert [call[0] for call in calls] == ["create", "pending", "status"]


def test_image_batch_cli_upload_approve_and_retry(monkeypatch, tmp_path, capsys):
    image = tmp_path / "scene.png"
    image.write_bytes(b"png")
    captured = {}
    monkeypatch.setattr(
        client,
        "upload_image_generation_candidate",
        lambda pid, batch, scene, input_hash, file_path, base: captured.update(
            {"pid": pid, "batch": batch, "scene": scene, "hash": input_hash, "file": file_path}
        )
        or {"candidateId": "c1"},
    )
    monkeypatch.setattr(
        client,
        "approve_image_generation_candidates",
        lambda pid, batch, selections, base: {"bound": selections},
    )
    monkeypatch.setattr(
        client,
        "retry_image_generation_batch",
        lambda pid, batch, base: {"status": "awaiting_agent"},
    )

    cli.main(
        [
            "image-batch-upload",
            "--pid",
            "p1",
            "--batch",
            "b1",
            "--scene",
            "s1",
            "--input-hash",
            "a" * 64,
            "--file",
            str(image),
        ]
    )
    assert json.loads(capsys.readouterr().out)["candidateId"] == "c1"
    assert captured["scene"] == "s1" and captured["file"] == str(image)
    cli.main(
        [
            "image-batch-approve",
            "--pid",
            "p1",
            "--batch",
            "b1",
            "--selections",
            '[{"sceneId":"s1","candidateId":"c1"}]',
        ]
    )
    assert json.loads(capsys.readouterr().out)["bound"][0]["candidateId"] == "c1"
    cli.main(["image-batch-retry", "--pid", "p1", "--batch", "b1"])
    assert json.loads(capsys.readouterr().out)["status"] == "awaiting_agent"


def test_client_upload_sends_form_fields_with_file(monkeypatch, tmp_path):
    image = tmp_path / "scene.png"
    image.write_bytes(b"png")
    captured = {}
    monkeypatch.setattr(client, "_request", lambda *args, **kwargs: captured.update(kwargs) or {"ok": True})

    client.upload_image_generation_candidate("p1", "b1", "s1", "a" * 64, str(image))

    assert captured["form"] == {"sceneId": "s1", "inputHash": "a" * 64}
    assert captured["files"] == {"file": str(image)}

