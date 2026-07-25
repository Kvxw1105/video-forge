from __future__ import annotations

from pathlib import Path
import sys
from typing import Any
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.lab_runner.run_store import RunStore


class DirectorStore:
    """Director compatibility layer over the Lab's single RunStore."""

    def __init__(self, store: RunStore | None = None):
        self.store = store or RunStore()

    @property
    def root(self) -> Path:
        return self.store.root

    def new_run_id(self) -> str:
        return f"dir_{uuid4().hex[:12]}"

    def run_dir(self, run_id: str) -> Path:
        return self.root / run_id

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = self.new_run_id()
        run = self.store.create(
            str(payload.get("recipeId") or "structured-knowledge-video"),
            1,
            run_id=run_id,
            runtime="director",
        )
        run.update({
            "task": str(payload.get("task") or "").strip(),
            "transport": "fake_pi",
            "mockTransport": True,
            "liveCallPerformed": False,
            "networkCalls": 0,
            "currentApprovalId": None,
            "messages": [],
            "artifacts": [],
            "metrics": {"mockTransport": True, "liveCallPerformed": False, "networkCalls": 0},
        })
        self.store.save(run)
        return run

    def list(self) -> list[dict[str, Any]]:
        return [run for run in self.store.list() if run.get("runtime") == "director"]

    def load(self, run_id: str) -> dict[str, Any]:
        return self.store.load(run_id)

    def save(self, run: dict[str, Any]) -> dict[str, Any]:
        self.store.save(run)
        return run

    def append_event(self, run_id: str, event: dict[str, Any]) -> dict[str, Any]:
        return self.store.append_event(run_id, event)

    def last_sequence(self, run_id: str) -> int:
        rows = self.store.events(run_id)
        return int(rows[-1]["sequence"]) if rows else 0

    def events(self, run_id: str, after: int = 0) -> list[dict[str, Any]]:
        return self.store.events(run_id, after=after)
