from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from agent.lab_runner.run_store import RunStore
from agent_runtime.director_service import DirectorService
from agent_runtime.director_store import DirectorStore
from agent_runtime.pi_transport import PiRpcTransport


class MockOpenAIHandler(BaseHTTPRequestHandler):
    requests: list[str] = []

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
        self.requests.append(f"POST {self.path}")
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return
        _ = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        time.sleep(0.25)  # Keep the approval observably ahead of agent_settled.
        payloads = [
            {"id": "mock", "choices": [{"delta": {"role": "assistant"}, "index": 0}]},
            {"id": "mock", "choices": [{"delta": {"content": "Pi reviewed the approved binding."}, "index": 0}]},
            {"id": "mock", "choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
        ]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for payload in payloads:
            self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode("utf-8"))
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def log_message(self, _format: str, *_args: object) -> None:
        return


def main() -> int:
    source = Path(os.environ.get("VIDEOFORGE_PI_SOURCE", r"D:\A-Project\video-forge-worktrees\pi-source"))
    entry = source / "packages" / "coding-agent" / "dist" / "rpc-entry.js"
    assert entry.is_file(), entry
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockOpenAIHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    old_agent_dir = os.environ.get("PI_CODING_AGENT_DIR")
    old_no_proxy = os.environ.get("NO_PROXY")
    old_no_proxy_lower = os.environ.get("no_proxy")
    # Node sidecars inherit desktop proxy settings. Keep this deterministic
    # local mock out of a configured upstream proxy.
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    os.environ["no_proxy"] = "127.0.0.1,localhost"
    calls: list[dict[str, Any]] = []
    try:
        with tempfile.TemporaryDirectory(prefix="videoforge-real-pi-") as temp:
            root = Path(temp)
            agent_dir = root / "pi-agent"
            agent_dir.mkdir()
            (agent_dir / "models.json").write_text(json.dumps({"providers": {"mock": {"baseUrl": f"http://127.0.0.1:{server.server_port}/v1", "apiKey": "local-test-key", "api": "openai-completions", "models": [{"id": "mock-model", "input": ["text"], "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}, "contextWindow": 8192, "maxTokens": 256}]}}}), encoding="utf-8")
            os.environ["PI_CODING_AGENT_DIR"] = str(agent_dir)
            transport = PiRpcTransport(["node", str(entry), "--mode", "rpc", "--model", "mock/mock-model", "--no-tools", "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-context-files"], cwd=ROOT, run_dir=lambda run_id: root / "runs" / run_id)

            def binder(*, batch_id: str, item_id: str, data: dict[str, Any]) -> dict[str, Any]:
                calls.append({"batchId": batch_id, "itemId": item_id, "data": data})
                return {"bound": True}

            service = DirectorService(store=DirectorStore(RunStore(root / "runs")), transport=transport, factory_binder=binder)
            run = service.create_run({"task": "Review then bind the vector asset.", "factoryContext": {"batchId": "batch_real_pi", "itemId": "item_a", "data": {"folder": "artifact://real-pi"}}})
            assert run["transport"] == "pi_rpc" and run["piPromptAccepted"] is True, run
            waiting = service.decide_approval(run["runId"], {"approvalId": run["approvals"][0]["approvalId"], "decision": "replace"})
            assert waiting["status"] == "waiting_pi", waiting
            for _ in range(80):
                final = service.get_run(run["runId"])
                if final["status"] == "succeeded":
                    break
                time.sleep(0.05)
            if final["status"] != "succeeded":
                raise AssertionError({"run": final, "events": service.events(run["runId"]), "mockRequests": MockOpenAIHandler.requests})
            assert len(calls) == 1, calls
            events = service.events(run["runId"])
            assert any(event["type"] == "agent.message.updated" and "Pi reviewed" in event.get("delta", "") for event in events), events
            assert any(event["type"] == "agent.settled" for event in events), events
            assert any(event["type"] == "lab.action.waiting_for_pi" for event in events), events
            assert any(event["type"] == "lab.action.dispatched" for event in events), events
            print({"runId": run["runId"], "status": final["status"], "events": len(events), "factoryCalls": len(calls)})
            transport.shutdown(run["runId"])
    finally:
        if old_agent_dir is None:
            os.environ.pop("PI_CODING_AGENT_DIR", None)
        else:
            os.environ["PI_CODING_AGENT_DIR"] = old_agent_dir
        if old_no_proxy is None:
            os.environ.pop("NO_PROXY", None)
        else:
            os.environ["NO_PROXY"] = old_no_proxy
        if old_no_proxy_lower is None:
            os.environ.pop("no_proxy", None)
        else:
            os.environ["no_proxy"] = old_no_proxy_lower
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
