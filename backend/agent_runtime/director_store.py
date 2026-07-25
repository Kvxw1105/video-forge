from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from config import PROJECTS_DIR


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


class DirectorStore:
    def __init__(self, root: Path | None = None):
        self.root = root or (PROJECTS_DIR / ".director-runs")
        self.root.mkdir(parents=True, exist_ok=True)

    def new_run_id(self) -> str:
        return f"dir_{uuid4().hex[:12]}"

    def run_dir(self, run_id: str) -> Path:
        return self.root / run_id

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = self.new_run_id()
        now = now_iso()
        run = {
            "runId": run_id,
            "status": "running",
            "task": str(payload.get("task") or "").strip(),
            "recipeId": payload.get("recipeId") or "structured-knowledge-video",
            "transport": "fake_pi",
            "mockTransport": True,
            "liveCallPerformed": False,
            "networkCalls": 0,
            "currentApprovalId": None,
            "createdAt": now,
            "updatedAt": now,
            "finishedAt": None,
            "messages": [],
            "approvals": [],
            "artifacts": [],
            "toolCalls": [],
            "metrics": {"mockTransport": True, "liveCallPerformed": False, "networkCalls": 0},
        }
        directory = self.run_dir(run_id)
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "events.jsonl").write_text("", encoding="utf-8")
        _atomic_json(directory / "run.json", run)
        return run

    def list(self) -> list[dict[str, Any]]:
        runs = []
        for directory in sorted(self.root.glob("dir_*"), key=lambda item: item.name, reverse=True):
            path = directory / "run.json"
            if not path.is_file():
                continue
            try:
                runs.append(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        return runs

    def load(self, run_id: str) -> dict[str, Any]:
        path = self.run_dir(run_id) / "run.json"
        if not path.is_file():
            raise FileNotFoundError(run_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, run: dict[str, Any]) -> dict[str, Any]:
        run["updatedAt"] = now_iso()
        _atomic_json(self.run_dir(run["runId"]) / "run.json", run)
        return run

    def append_event(self, run_id: str, event: dict[str, Any]) -> dict[str, Any]:
        sequence = self.last_sequence(run_id) + 1
        payload = {"sequence": sequence, "time": now_iso(), **event}
        with (self.run_dir(run_id) / "events.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return payload

    def last_sequence(self, run_id: str) -> int:
        rows = self.events(run_id)
        return int(rows[-1]["sequence"]) if rows else 0

    def events(self, run_id: str, after: int = 0) -> list[dict[str, Any]]:
        path = self.run_dir(run_id) / "events.jsonl"
        if not path.is_file():
            raise FileNotFoundError(run_id)
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if int(event.get("sequence") or 0) > after:
                rows.append(event)
        return rows
