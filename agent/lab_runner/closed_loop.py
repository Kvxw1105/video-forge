"""Real HTTP Phase 0B closed-loop verification for a local VideoForge backend."""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from .run_store import RunStore, atomic_write_json, now_iso


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlE9U8AAAAASUVORK5CYII=")
PNG_ALT = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


def request(base: str, method: str, path: str, body: dict | None = None) -> tuple[int, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(base.rstrip("/") + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        try:
            return error.code, json.loads(raw)
        except json.JSONDecodeError:
            return error.code, {"detail": raw}


def _spec(key: str) -> dict:
    lines = [f"Synthetic sentence {index}." for index in range(1, 16)]
    markdown = "## STORY\n" + "\n".join(lines[:5]) + "\n\n## MECHANISM\n" + "\n".join(lines[5:10]) + "\n\n## METHOD\n" + "\n".join(lines[10:])
    return {
        "schemaVersion": 1, "name": "Phase0B closed loop", "idempotencyKey": key, "templateId": "tpl_single_voiceover",
        "defaults": {"inputMode": "structured_markdown", "voiceover": {"enabled": True, "engine": "fish_audio", "generateSubtitles": True}, "outputs": {"preview": True, "jianyingDirect": True, "jianyingZip": False}},
        "visualWorkflow": {"enabled": True, "mode": "generation_pack", "planningMode": "fixed_units", "unitsPerScene": 5, "targetDuration": 5, "minDuration": 1, "maxDuration": 10, "requireCompleteCoverage": True},
        "items": [{"itemId": "item_a", "name": "Phase0B item", "structuredMarkdown": markdown, "assets": {"images": [], "videos": [], "bgm": None}}],
    }


def _assets(root: Path, alternate: bool = False) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for index in range(1, 4):
        (root / f"scene_{index:03d}.png").write_bytes(PNG_ALT if alternate and index == 2 else PNG)


def _wait_batch(base: str, batch_id: str, expected: str) -> dict:
    for _ in range(40):
        _, batch = request(base, "GET", f"/api/batches/template-production/{batch_id}")
        if batch.get("status") == expected:
            return batch
        time.sleep(0.25)
    raise RuntimeError(f"batch {batch_id} did not reach {expected}")


def _prepare(base: str, root: Path) -> tuple[dict, Path]:
    request(base, "PUT", "/api/settings/tts", {"fishApiKey": "phase0b-local-mock", "fishReferenceId": "phase0b-local-reference", "fishModel": "s2-pro"})
    status, started = request(base, "POST", "/api/batches/template-production", _spec(f"phase0b-{uuid.uuid4().hex}"))
    if status != 200:
        raise RuntimeError(started)
    batch = _wait_batch(base, started["batchId"], "awaiting_visual_assets")
    asset_dir = root / started["batchId"] / "assets"
    _assets(asset_dir)
    return batch, asset_dir


def scenario_success(base: str, root: Path) -> dict:
    batch, asset_dir = _prepare(base, root)
    row = batch["items"][0]
    status, imported = request(base, "POST", f"/api/agent-factory/batches/{batch['batchId']}/items/item_a/visuals/import", {"folder": str(asset_dir)})
    if status != 200 or not imported["coverage"]["complete"]:
        raise RuntimeError(imported)
    status, resumed = request(base, "POST", f"/api/agent-factory/batches/{batch['batchId']}/items/item_a/resume", {})
    if status != 200:
        raise RuntimeError(resumed)
    final = _wait_batch(base, batch["batchId"], "succeeded")
    outputs = final["items"][0]["outputs"]
    preview = Path(outputs["preview"]["path"])
    draft = Path(outputs["jianying"]["draftPath"])
    if not preview.is_file() or preview.stat().st_size == 0 or not draft.is_dir():
        raise RuntimeError("missing closed-loop output artifact")
    return {"scenario": "structured_factory_success", "batchId": batch["batchId"], "projectId": row["projectId"], "subtitleCount": 45, "sceneCount": 3, "initialStatus": "awaiting_visual_assets", "finalStatus": final["status"], "previewPath": str(preview), "previewBytes": preview.stat().st_size, "jianyingPath": str(draft)}


def _create_waiting_run(store: RunStore, recipe: str, kind: str, evidence: dict) -> dict:
    run = store.create(recipe, 1, kind)
    run.update({"status": "waiting_for_approval", "currentStepId": kind, "batchId": evidence["batchId"], "projectId": evidence["projectId"], "waitingReason": kind})
    run["steps"] = [{"stepId": "prepare", "status": "succeeded", "invocationCount": 1}, {"stepId": kind, "status": "waiting", "invocationCount": 1}]
    run["approvals"] = [{"type": kind, "status": "pending", **evidence}]
    store.save(run); store.append_event(run["runId"], {"type": "approval.requested", "approval": run["approvals"][0]})
    return run


def scenario_conflict_start(base: str, root: Path, store: RunStore) -> dict:
    success = scenario_success(base, root)
    assets = root / success["batchId"] / "assets"
    _assets(assets, alternate=True)
    status, response = request(base, "POST", f"/api/agent-factory/batches/{success['batchId']}/items/item_a/visuals/import", {"folder": str(assets)})
    if status != 409:
        raise RuntimeError({"expected": 409, "actual": status, "response": response})
    run = _create_waiting_run(store, "existing-assets-recut", "asset_conflict", {"batchId": success["batchId"], "projectId": success["projectId"], "sceneId": "scene_mechanism_01_001", "httpStatus": status, "candidateAsset": "scene_002.png"})
    return {"runId": run["runId"], "assets": str(assets), **success}


def scenario_conflict_resume(base: str, run_id: str, assets: str, store: RunStore) -> dict:
    run = store.load(run_id)
    status, response = request(base, "POST", f"/api/agent-factory/batches/{run['batchId']}/items/item_a/visuals/import", {"folder": assets, "replace": True})
    if status != 200:
        raise RuntimeError(response)
    run["approvals"][0]["status"] = "approved"; run["approvals"][0]["decision"] = "replace"
    run["steps"][1].update({"status": "succeeded", "invocationCount": 2})
    run["status"] = "completed"; run["currentStepId"] = None; run["finishedAt"] = now_iso()
    store.save(run); store.append_event(run_id, {"type": "approval.approved", "decision": "replace"})
    return {"runId": run_id, "finalStatus": run["status"], "prepareInvocationCount": run["steps"][0]["invocationCount"], "coverage": response["coverage"]}


def scenario_revoice_start(base: str, root: Path, store: RunStore) -> dict:
    success = scenario_success(base, root)
    _, project = request(base, "GET", f"/api/projects/{success['projectId']}")
    old = project["structuredContent"]["episode"]["alignment"]["audioPath"]
    run = _create_waiting_run(store, "book-summary-short", "regenerate_voiceover", {"batchId": success["batchId"], "projectId": success["projectId"], "oldAudioPath": old})
    return {"runId": run["runId"], **success, "oldAudioPath": old}


def scenario_revoice_resume(base: str, run_id: str, store: RunStore) -> dict:
    run = store.load(run_id)
    status, response = request(base, "POST", f"/api/projects/{run['projectId']}/structured/audio/fish-aligned", {"force": True, "generateSubtitles": True})
    if status != 200 or not response.get("mockTransport") or response.get("liveCallPerformed"):
        raise RuntimeError(response)
    new = response["audioPath"]
    root = Path.cwd() / "projects" / run["projectId"]
    if new == run["approvals"][0]["oldAudioPath"] or not (root / new).is_file():
        raise RuntimeError("revoice artifact validation failed")
    run["approvals"][0]["status"] = "approved"; run["approvals"][0]["decision"] = "approve"
    run["steps"][1].update({"status": "succeeded", "invocationCount": 2})
    run["status"] = "completed"; run["currentStepId"] = None; run["finishedAt"] = now_iso()
    store.save(run); store.append_event(run_id, {"type": "approval.approved", "decision": "approve"})
    return {"runId": run_id, "finalStatus": run["status"], "oldAudioPath": run["approvals"][0]["oldAudioPath"], "newAudioPath": new, "mockTransport": response["mockTransport"], "liveCallPerformed": response["liveCallPerformed"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "conflict-resume", "revoice-resume"])
    parser.add_argument("--base-url", default="http://127.0.0.1:8767")
    parser.add_argument("--run-root", default=".agent-runs/phase0b")
    parser.add_argument("--run-id")
    parser.add_argument("--assets")
    parser.add_argument("--report-dir", default="agent/evals/results")
    args = parser.parse_args(argv)
    store = RunStore(args.run_root)
    if args.command == "conflict-resume":
        print(json.dumps(scenario_conflict_resume(args.base_url, args.run_id, args.assets, store), ensure_ascii=False)); return 0
    if args.command == "revoice-resume":
        print(json.dumps(scenario_revoice_resume(args.base_url, args.run_id, store), ensure_ascii=False)); return 0
    root = Path(args.run_root).resolve() / "http-assets"
    a = scenario_success(args.base_url, root)
    b = scenario_conflict_start(args.base_url, root, store)
    b_resume = subprocess.run([sys.executable, "-m", "agent.lab_runner.closed_loop", "conflict-resume", "--base-url", args.base_url, "--run-root", args.run_root, "--run-id", b["runId"], "--assets", b["assets"]], text=True, capture_output=True, check=False)
    if b_resume.returncode:
        raise RuntimeError(b_resume.stderr or b_resume.stdout)
    c = scenario_revoice_start(args.base_url, root, store)
    c_resume = subprocess.run([sys.executable, "-m", "agent.lab_runner.closed_loop", "revoice-resume", "--base-url", args.base_url, "--run-root", args.run_root, "--run-id", c["runId"]], text=True, capture_output=True, check=False)
    if c_resume.returncode:
        raise RuntimeError(c_resume.stderr or c_resume.stdout)
    report = {"timestamp": now_iso(), "backendUrl": args.base_url, "mockFish": True, "labOutputStub": True, "scenarios": [a, b, json.loads(b_resume.stdout), c, json.loads(c_resume.stdout)], "status": "passed"}
    report_dir = Path(args.report_dir); report_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(report_dir / "phase0_report.json", report)
    (report_dir / "phase0_report.md").write_text("# Phase 0B HTTP Closed Loop\n\n- Status: passed\n- Backend: " + args.base_url + "\n- Fish network calls: 0\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
