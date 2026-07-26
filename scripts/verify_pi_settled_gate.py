from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from agent.lab_runner.run_store import RunStore
from agent_runtime.director_service import DirectorService
from agent_runtime.director_store import DirectorStore


class ControlledPiTransport:
    name = "controlled_pi"

    def create_session(self, run_id: str, task: str) -> dict[str, Any]:
        return {"sessionId": f"pi_{run_id}", "mockTransport": False, "liveCallPerformed": False, "networkCalls": None}

    def initial_events(self, run_id: str, task: str) -> list[dict[str, Any]]:
        return [{"type": "pi.session.created", "runId": run_id, "transport": self.name}]

    def prompt(self, run_id: str, message: str) -> dict[str, Any]:
        return {"accepted": True, "settled": False}


def main() -> int:
    calls: list[dict[str, Any]] = []

    def binder(*, batch_id: str, item_id: str, data: dict[str, Any]) -> dict[str, Any]:
        calls.append({"batchId": batch_id, "itemId": item_id, "data": data})
        return {"bound": True}

    with tempfile.TemporaryDirectory(prefix="videoforge-pi-gate-") as temp:
        service = DirectorService(store=DirectorStore(RunStore(Path(temp))), transport=ControlledPiTransport(), factory_binder=binder)
        run = service.create_run({"task": "Wait for Pi before binding.", "factoryContext": {"batchId": "batch_gate", "itemId": "item_a", "data": {"folder": "artifact://gate"}}})
        assert run["piState"] == "running", run
        approval = service.decide_approval(run["runId"], {"approvalId": run["approvals"][0]["approvalId"], "decision": "replace"})
        assert approval["status"] == "waiting_pi", approval
        assert calls == [], calls
        service._on_pi_event(run["runId"], {"type": "agent.settled", "piEventType": "agent_settled"})
        final = service.get_run(run["runId"])
        assert final["piState"] == "settled", final
        assert final["status"] == "succeeded", final
        assert len(calls) == 1, calls
        events = service.events(run["runId"])
        assert any(event["type"] == "lab.action.waiting_for_pi" for event in events), events
        assert any(event["type"] == "lab.action.dispatched" for event in events), events
        print({"runId": run["runId"], "status": final["status"], "factoryCalls": len(calls)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
