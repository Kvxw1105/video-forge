"""Durable two-item Agent Factory platform flow, using the shared test fixture."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from main import create_app
from services import project_service, template_batch_service as batches
from test_agent_factory_two_stage import _mock_fish_alignment, _structured_factory_spec, _structured_markdown


def _outputs(root, calls, *, fail_item=None):
    def run(batch_id, item_id, _project_id, _outputs, result, **kwargs):
        item_root = root / item_id; item_root.mkdir(parents=True, exist_ok=True)
        input_hash = kwargs["input_hash"]
        if not result.get("previewUrl"):
            result["phase"] = "rendering_preview"; calls[item_id]["preview"] += 1
            preview = item_root / "preview.mp4"; preview.write_bytes(b"preview")
            result["previewUrl"] = f"/{item_id}/preview.mp4"
            result.setdefault("outputs", {})["preview"] = {"status": "succeeded", "path": str(preview), "inputHash": input_hash}
        if not result.get("jianyingDraftPath"):
            result["phase"] = "exporting_jianying"; calls[item_id]["jianying"] += 1
            if item_id == fail_item and calls[item_id]["jianying"] == 1:
                raise RuntimeError("controlled JianYing failure")
            draft = item_root / "draft"; draft.mkdir(exist_ok=True)
            result["jianyingDraftPath"] = str(draft)
            result.setdefault("outputs", {})["jianying"] = {"status": "succeeded", "draftPath": str(draft), "inputHash": input_hash}
    return run


def _start(monkeypatch, tmp_path, key):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(batches, "PROJECTS_DIR", tmp_path)
    sentences = [f"sentence {index}." for index in range(1, 16)]
    _mock_fish_alignment(monkeypatch, sentences)
    markdown = _structured_markdown(sentences)
    items = [
        {"itemId": "item_a", "name": "Item A", "structuredMarkdown": markdown, "assets": {"images": [], "videos": [], "bgm": None}},
        {"itemId": "item_b", "name": "Item B", "structuredMarkdown": markdown, "assets": {"images": [], "videos": [], "bgm": None}},
    ]
    spec = _structured_factory_spec(key, items)
    started = batches.start(spec, lambda *_: {"jobId": "job"})
    batch = batches.execute(started["batchId"])
    assert batch["status"] == "awaiting_visual_assets" and batch["progress"] == 100 and batch["currentItemId"] is None
    assert {row["status"] for row in batch["items"]} == {"awaiting_visual_assets"}
    assert len({row["projectId"] for row in batch["items"]}) == 2
    assert len({row["visualPlanId"] for row in batch["items"]}) == 2
    for row in batch["items"]:
        project = project_service.get_project(row["projectId"])
        assert len(project.subtitles) == 15
        assert len(project.structuredContent.episode.bindings) == 3
        assert len(project.structuredContent.episode.visualPlan.scenes) == 3
        assert Path(row["generationPackPath"]).is_dir()
    return TestClient(create_app(), raise_server_exceptions=False), spec, started["batchId"], batch


def _assets(root, count):
    root.mkdir(parents=True, exist_ok=True)
    (root / "scene_001.png").write_bytes(b"png")
    (root / "scene_002.mp4").write_bytes(b"mp4")
    if count == 3:
        (root / "scene_003.png").write_bytes(b"png")


def test_two_item_factory_pause_resume_recovery_and_persistence(monkeypatch, tmp_path):
    client, spec, batch_id, first = _start(monkeypatch, tmp_path, "platform_two_item")
    assert sum(len(project_service.get_project(row["projectId"]).structuredContent.episode.visualPlan.scenes) for row in first["items"]) == 6
    folders = {"item_a": tmp_path / "a", "item_b": tmp_path / "b"}
    _assets(folders["item_a"], 3); _assets(folders["item_b"], 2)
    for item_id in ("item_a", "item_b"):
        response = client.post(f"/api/agent-factory/batches/{batch_id}/items/{item_id}/visuals/import", json={"folder": str(folders[item_id])})
        assert response.status_code == 200
    partial = batches.get(batch_id)
    states = {row["itemId"]: row["status"] for row in partial["items"]}
    assert states == {"item_a": "ready_to_resume", "item_b": "awaiting_visual_assets"}
    assert partial["status"] == "awaiting_visual_assets"
    calls = {item: {"preview": 0, "jianying": 0} for item in states}
    monkeypatch.setattr(batches, "_run_item_outputs", _outputs(tmp_path / "outputs", calls))
    resumed = client.post(f"/api/agent-factory/batches/{batch_id}/resume", json={}).json()
    assert resumed == {"batchId": batch_id, "status": "awaiting_visual_assets", "resumedItems": ["item_a"], "waitingItems": ["item_b"], "skippedItems": [], "failedItems": []}
    assert calls == {"item_a": {"preview": 1, "jianying": 1}, "item_b": {"preview": 0, "jianying": 0}}

    # Reload entirely from durable manifests, then complete only the waiting item.
    reloaded = batches.get(batch_id)
    assert reloaded["status"] == "awaiting_visual_assets"
    _assets(folders["item_b"], 3)
    assert client.post(f"/api/agent-factory/batches/{batch_id}/items/item_b/visuals/import", json={"folder": str(folders["item_b"])}).status_code == 200
    continued = client.post(f"/api/agent-factory/batches/{batch_id}/continue", json={}).json()
    assert continued["resumedItems"] == ["item_b"] and continued["status"] == "succeeded"
    assert calls == {"item_a": {"preview": 1, "jianying": 1}, "item_b": {"preview": 1, "jianying": 1}}
    final = batches.get(batch_id)
    assert final["status"] == "succeeded"
    assert len({row["previewUrl"] for row in final["items"]}) == 2
    assert len({row["jianyingDraftPath"] for row in final["items"]}) == 2
    for row in final["items"]:
        assert len(project_service.get_project(row["projectId"]).assets) == 3
        assert Path(row["outputs"]["preview"]["path"]).is_file()
        assert Path(row["outputs"]["jianying"]["draftPath"]).is_dir()
    assert batches.start(spec, lambda *_: {"jobId": "unused"})["idempotent"] is True
    assert client.post(f"/api/agent-factory/batches/{batch_id}/resume", json={}).json()["skippedItems"] == ["item_a", "item_b"]
    assert client.post(f"/api/agent-factory/batches/{batch_id}/continue", json={}).json()["status"] == "succeeded"
    assert calls == {"item_a": {"preview": 1, "jianying": 1}, "item_b": {"preview": 1, "jianying": 1}}


def test_two_item_factory_recovers_only_failed_jianying_item(monkeypatch, tmp_path):
    client, _, batch_id, _ = _start(monkeypatch, tmp_path, "platform_partial_failure")
    for item_id in ("item_a", "item_b"):
        folder = tmp_path / item_id; _assets(folder, 3)
        assert client.post(f"/api/agent-factory/batches/{batch_id}/items/{item_id}/visuals/import", json={"folder": str(folder)}).status_code == 200
    calls = {item: {"preview": 0, "jianying": 0} for item in ("item_a", "item_b")}
    monkeypatch.setattr(batches, "_run_item_outputs", _outputs(tmp_path / "outputs", calls, fail_item="item_b"))
    first = client.post(f"/api/agent-factory/batches/{batch_id}/resume", json={}).json()
    assert first["resumedItems"] == ["item_a"] and first["failedItems"] == ["item_b"]
    failed = batches.get(batch_id)
    assert failed["status"] == "partial"
    assert next(row for row in failed["items"] if row["itemId"] == "item_b")["phase"] == "exporting_jianying"
    second = client.post(f"/api/agent-factory/batches/{batch_id}/resume", json={}).json()
    assert second["resumedItems"] == ["item_b"] and second["status"] == "succeeded"
    assert calls == {"item_a": {"preview": 1, "jianying": 1}, "item_b": {"preview": 1, "jianying": 2}}
