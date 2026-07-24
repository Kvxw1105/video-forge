import json

from agent.lab_runner.run_store import RunStore, atomic_write_json


def test_run_log_atomic_write_and_resume(tmp_path):
    store = RunStore(tmp_path)
    run = store.create("structured-knowledge-video", 1, "case")
    run["status"] = "waiting_assets"
    store.save(run)
    loaded = store.load(run["runId"])
    assert loaded["status"] == "waiting_assets"
    assert (tmp_path / run["runId"] / "events.jsonl").exists()


def test_log_sanitization_removes_credentials_and_user_paths(tmp_path):
    path = tmp_path / "run.json"
    atomic_write_json(
        path,
        {
            "path": "C:\\Users\\kvxkf\\secret\\project.json",
            "auth": "Authorization" + ": Bearer " + "sk-" + "actualsecret",
            "fishApiKey": "configured",
        },
    )
    text = path.read_text(encoding="utf-8")
    assert "C:\\Users\\" not in text
    assert "Authorization:" not in text
    assert "sk-" not in text
    assert json.loads(text)["fishApiKey"] == "<redacted>"
