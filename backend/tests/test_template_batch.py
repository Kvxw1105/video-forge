import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import project_service, template_batch_service as batches


def _spec(items, **defaults):
    return {"schemaVersion": 1, "name": "batch", "idempotencyKey": "batch_test_01", "templateId": "tpl_single_voiceover", "defaults": {"ratio": "9:16", "inputMode": "plain_script", "voiceover": {"enabled": False, "engine": "none"}, "outputs": {"preview": False, "jianyingDirect": False, "jianyingZip": False}, "continueOnError": True, **defaults}, "items": items}


def _item(item_id, script="text", **extra):
    return {"itemId": item_id, "name": item_id, "script": script, "assets": {"images": [], "videos": [], "bgm": None}, **extra}


@pytest.fixture(autouse=True)
def _isolated_batch_data(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(batches, "PROJECTS_DIR", tmp_path)


def test_plan_rejects_missing_script_unknown_variable_and_unknown_section(tmp_path):
    missing = batches.plan(_spec([_item("one", script="")]))
    assert not missing["valid"] and missing["errors"][0]["code"] == "script_required"
    bad_variable = _spec([_item("one")]); bad_variable["items"][0]["overrides"] = {"overlays": {"title": {"text": "{{unknown}}"}}}
    # Variables are checked during the production projection, before any project is persisted.
    with pytest.raises(batches.BatchError, match="Unknown template variable"):
        batches._render_variables(bad_variable["items"][0]["overrides"], {"title": "x"})
    structured = _spec([_item("one", structuredMarkdown="## UNKNOWN\ntext")], inputMode="structured_markdown")
    result = batches.plan(structured)
    assert not result["valid"] and "needs_mapping" in result["warnings"][0]


def test_idempotent_start_does_not_create_a_second_batch():
    calls = []
    def fake_job(kind, work):
        calls.append(kind); return {"jobId": "job_1"}
    spec = _spec([_item("one")])
    first = batches.start(spec, fake_job)
    second = batches.start(spec, fake_job)
    assert first["batchId"] == second["batchId"]
    assert second["idempotent"] is True and calls == ["template_batch"]
    conflict = dict(spec); conflict["name"] = "changed"
    with pytest.raises(batches.BatchError) as exc:
        batches.start(conflict, fake_job)
    assert exc.value.code == "idempotency_key_conflict"


def test_execute_continue_and_resume_skips_successful_items(tmp_path):
    good = tmp_path / "good.png"; good.write_bytes(b"png")
    spec = _spec([_item("a"), _item("b", assets={"images": [str(good)], "videos": [], "bgm": None}), _item("c")])
    started = batches.start(spec, lambda kind, work: {"jobId": "job_1"})
    batch_id = started["batchId"]
    good.unlink()
    final = batches.execute(batch_id)
    assert final["status"] == "partial"
    assert [item["status"] for item in final["items"]] == ["succeeded", "failed", "succeeded"]
    original_ids = [item["projectId"] for item in final["items"] if item["status"] == "succeeded"]
    saved_spec = json.loads((tmp_path / ".batches" / batch_id / "spec.json").read_text(encoding="utf-8"))
    good.write_bytes(b"png")
    batches._atomic_json(tmp_path / ".batches" / batch_id / "spec.json", saved_spec)
    resumed = batches.resume(batch_id, lambda kind, work: {"jobId": "job_2"})
    assert resumed["status"] == "queued"
    final = batches.execute(batch_id)
    assert final["status"] == "succeeded"
    assert [item["projectId"] for item in final["items"] if item["itemId"] in {"a", "c"}] == original_ids
    assert [item["attempts"] for item in final["items"]] == [1, 2, 1]
    assert (tmp_path / ".batches" / batch_id / "events.jsonl").exists()
