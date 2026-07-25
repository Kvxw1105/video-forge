from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from agent_runtime.director_service import DirectorService
from agent_runtime.director_store import DirectorStore
from agent.lab_runner.run_store import RunStore


def main() -> int:
    calls: list[dict] = []

    def binder(*, batch_id: str, item_id: str, data: dict) -> dict:
        calls.append({"batchId": batch_id, "itemId": item_id, "data": data})
        return {"batchId": batch_id, "itemId": item_id, "bound": True}

    with tempfile.TemporaryDirectory(prefix="videoforge-director-") as temp:
        service = DirectorService(store=DirectorStore(RunStore(Path(temp))), factory_binder=binder)
        run = service.create_run({
            "task": "Bind the reviewed vector asset.",
            "factoryContext": {"batchId": "batch_demo", "itemId": "item_a", "data": {"folder": "artifact://reviewed-vector"}},
        })
        final = service.decide_approval(run["runId"], {"approvalId": run["approvals"][0]["approvalId"], "decision": "replace"})
        assert final["status"] == "succeeded", final
        assert calls == [{"batchId": "batch_demo", "itemId": "item_a", "data": {"folder": "artifact://reviewed-vector"}}], calls
        assert final["labActions"][0]["factoryResult"]["bound"] is True, final
        assert any(event["type"] == "lab.action.dispatched" for event in service.events(run["runId"])), final
        print({"runId": run["runId"], "factoryCalls": len(calls), "status": final["status"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
