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
from agent_runtime.director_proposals import proposal_instruction, proposals_from_agent_end


class PlannedPiTransport:
    name = "planned_pi"

    def __init__(self) -> None:
        self.event_sink = None

    def set_event_sink(self, event_sink: Any) -> None:
        self.event_sink = event_sink

    def create_session(self, run_id: str, task: str) -> dict[str, Any]:
        return {"sessionId": f"pi_{run_id}", "mockTransport": False, "liveCallPerformed": False, "networkCalls": None}

    def initial_events(self, run_id: str, task: str) -> list[dict[str, Any]]:
        return []

    def prompt(self, run_id: str, message: str) -> dict[str, Any]:
        assert "videoforgeActionProposals" in message
        # Exercise the real race: Pi can finish before prompt() returns.
        assert self.event_sink is not None
        self.event_sink(run_id, {
            "type": "agent.turn.ended",
            "piEventType": "agent_end",
            "piEvent": {"messages": [{"role": "assistant", "content": [{"type": "text", "text": '{"videoforgeActionProposals":[{"operation":"replace_scene_asset","sceneId":"scene_001","reason":"The timing-aligned card replaces the current scene asset."}]}' }]}]},
        })
        return {"accepted": True, "settled": False}


def main() -> int:
    dynamic = proposals_from_agent_end({"piEvent": {"messages": [{"role": "assistant", "content": "{\"videoforgeActionProposals\":[{\"operation\":\"replace_scene_asset\",\"sceneId\":\"srt_0001\",\"reason\":\"subtitle aligned\"}]}"}]}}, scene_id="srt_0001")
    assert dynamic and dynamic[0]["sceneId"] == "srt_0001"
    assert '"sceneId": "srt_0001"' in proposal_instruction("srt_0001")
    with tempfile.TemporaryDirectory(prefix="videoforge-action-proposals-") as temp:
        service = DirectorService(store=DirectorStore(RunStore(Path(temp))), transport=PlannedPiTransport())
        run = service.create_run({"task": "Review the current scene asset."})
        approval = run["approvals"][0]
        assert approval["actionProposal"]["approvalId"] == approval["approvalId"], run
        assert len(run["actionProposals"]) == 1, run
        service._on_pi_event(run["runId"], {
            "type": "agent.turn.ended",
            "piEventType": "agent_end",
            "piEvent": {"messages": [{"role": "assistant", "content": [{"type": "text", "text": "```json\n{\"videoforgeActionProposals\":[{\"operation\":\"replace_scene_asset\",\"sceneId\":\"scene_001\",\"reason\":\"The timing-aligned card replaces the current scene asset.\"},{\"operation\":\"shell\",\"sceneId\":\"scene_001\",\"reason\":\"must not pass\"}]}\n```"}]}]},
        })
        result = service.get_run(run["runId"])
        assert len(result["actionProposals"]) == 1, result
        proposal = result["actionProposals"][0]
        assert proposal["status"] == "pending_approval" and proposal["approvalId"] == approval["approvalId"], result
        assert result["approvals"][0]["actionProposal"]["proposalId"] == proposal["proposalId"], result
        events = service.events(run["runId"])
        assert any(event["type"] == "approval.proposed" for event in events), events
        # Replayed Pi events do not create another approval or a second execution path.
        service._on_pi_event(run["runId"], events[-2] if False else {
            "type": "agent.turn.ended", "piEventType": "agent_end", "piEvent": {"messages": [{"role": "assistant", "content": [{"type": "text", "text": '{"videoforgeActionProposals":[{"operation":"replace_scene_asset","sceneId":"scene_001","reason":"The timing-aligned card replaces the current scene asset."}]}' }]}]}
        })
        assert len(service.get_run(run["runId"])["actionProposals"]) == 1
        rejected = service.decide_approval(run["runId"], {"approvalId": approval["approvalId"], "decision": "reject"})
        assert rejected["status"] == "rejected", rejected
        assert rejected["approvals"][0]["status"] == "rejected", rejected
        assert rejected["actionProposals"][0]["status"] == "rejected", rejected
        assert not any(event["type"] == "run.completed" for event in service.events(run["runId"])), rejected
        print({"runId": run["runId"], "proposals": 1, "approval": approval["approvalId"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
