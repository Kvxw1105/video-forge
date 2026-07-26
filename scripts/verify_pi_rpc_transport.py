from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from agent_runtime.pi_transport import PiRpcTransport


def main() -> int:
    source = Path(os.environ.get("VIDEOFORGE_PI_SOURCE", r"D:\A-Project\video-forge-worktrees\pi-source"))
    entry = source / "packages" / "coding-agent" / "dist" / "rpc-entry.js"
    assert entry.is_file(), f"Pi RPC entry is missing: {entry}"
    os.environ.setdefault("VIDEOFORGE_PI_SOURCE", str(source))
    with tempfile.TemporaryDirectory(prefix="videoforge-pi-rpc-") as temp:
        root = Path(temp)
        transport = PiRpcTransport.from_environment(run_dir=lambda run_id: root / run_id, repo_root=ROOT)
        session = transport.create_session("rpc_smoke", "Verify Pi RPC session startup without an agent turn.")
        assert session["mockTransport"] is False, session
        assert session["sessionId"], session
        events = transport.initial_events("rpc_smoke", "smoke")
        assert any(event["type"] == "pi.sidecar.ready" for event in events), events
        transport.abort("rpc_smoke")
        transport.shutdown("rpc_smoke")
        print({"transport": transport.name, "sessionId": session["sessionId"], "events": len(events)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
