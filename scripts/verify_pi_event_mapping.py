from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from agent_runtime.pi_transport import normalize_pi_event
from agent_runtime.director_store import DirectorStore
from agent.lab_runner.run_store import RunStore


def main() -> int:
    tool = normalize_pi_event({"type": "tool_execution_end", "toolCallId": "tc_1", "toolName": "videoforge_recipe_contract", "isError": False})
    message = normalize_pi_event({"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "scene"}})
    assert tool["type"] == "tool.call.succeeded", tool
    assert tool["toolCallId"] == "tc_1", tool
    assert message == {"type": "agent.message.updated", "piEventType": "message_update", "piEvent": {"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "scene"}}, "delta": "scene"}, message
    with tempfile.TemporaryDirectory(prefix="videoforge-event-lock-") as temp:
        store = DirectorStore(RunStore(Path(temp)))
        run = store.create({"task": "event lock"})
        threads = [threading.Thread(target=store.append_event, args=(run["runId"], {"type": "pi.event", "index": index})) for index in range(16)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert [item["sequence"] for item in store.events(run["runId"])] == list(range(1, 17))
    print({"toolEvent": tool["type"], "messageEvent": message["type"], "concurrentEvents": 16})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
