from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

from main import create_app


def main() -> int:
    client = TestClient(create_app())
    version = client.get("/api/version")
    assert version.status_code == 200, version.text
    started = client.post("/api/director/runs", json={"task": "把这篇文案生成一个可预览、可导入剪映的视频草稿。"})
    assert started.status_code == 200, started.text
    run = started.json()
    assert run["status"] == "waiting_approval", run
    assert run["runtime"] == "director", run
    assert run["mockTransport"] is True
    assert run["liveCallPerformed"] is False
    assert run["networkCalls"] == 0
    events = client.get(f"/api/director/runs/{run['runId']}/events").json()["events"]
    assert events[0]["sequence"] == 1
    assert any(item["type"] == "approval.requested" for item in events)
    approval = run["approvals"][0]
    decided = client.post(f"/api/director/runs/{run['runId']}/approvals", json={"approvalId": approval["approvalId"], "decision": "replace"})
    assert decided.status_code == 200, decided.text
    final = decided.json()
    assert final["status"] == "succeeded", final
    artifacts = client.get(f"/api/director/runs/{run['runId']}/artifacts").json()["artifacts"]
    paths = [Path(item["path"]) for item in artifacts]
    assert all(".agent-runs" in path.parts for path in paths), paths
    assert any(path.suffix == ".svg" and path.is_file() for path in paths), paths
    assert any(path.name == "preview-manifest.json" and path.is_file() for path in paths), paths
    assert any(path.name == "jianying-draft" and path.is_dir() for path in paths), paths
    replay = client.get(f"/api/director/runs/{run['runId']}/events?after=2").json()["events"]
    assert replay and all(item["sequence"] > 2 for item in replay)
    print({"runId": run["runId"], "status": final["status"], "artifacts": len(artifacts), "commit": version.json()["commit"][:8]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
