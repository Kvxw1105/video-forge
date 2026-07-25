from __future__ import annotations

from typing import Any


class FakePiTransport:
    name = "fake_pi"

    def create_session(self, run_id: str, task: str) -> dict[str, Any]:
        return {
            "sessionId": f"fake_pi_{run_id}",
            "mockTransport": True,
            "liveCallPerformed": False,
            "networkCalls": 0,
            "task": task,
        }

    def initial_events(self, run_id: str, task: str) -> list[dict[str, Any]]:
        return [
            {"type": "pi.session.created", "runId": run_id, "transport": self.name},
            {"type": "agent.message", "role": "assistant", "content": "Director Run created; preparing the first structured scene asset."},
            {"type": "tool.call.started", "toolName": "vector_card.generate_scene_asset", "sceneId": "scene_001"},
        ]
