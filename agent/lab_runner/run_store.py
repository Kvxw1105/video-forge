from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECRET_PATTERNS = [
    re.compile(r"C:\\Users\\[^\\\s\"]+", re.IGNORECASE),
    re.compile(r"Authorization:\s*[^\s\"']+", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: ("<redacted>" if key.lower() in {"fishapikey", "authorization", "cookie"} and val else sanitize(val)) for key, val in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        text = value
        for pattern in SECRET_PATTERNS:
            text = pattern.sub("<redacted>", text)
        return text
    return value


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(sanitize(data), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


class RunStore:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root else Path(__file__).resolve().parents[2] / ".agent-runs"
        self.root.mkdir(parents=True, exist_ok=True)

    def new_run_id(self) -> str:
        return f"run_{uuid.uuid4().hex[:12]}"

    def run_dir(self, run_id: str) -> Path:
        return self.root / run_id

    def create(
        self,
        recipe_id: str,
        recipe_version: int,
        case_id: str | None = None,
        *,
        run_id: str | None = None,
        runtime: str = "phase0_lab_runner",
    ) -> dict[str, Any]:
        run_id = run_id or self.new_run_id()
        data = {
            "runId": run_id,
            "recipeId": recipe_id,
            "recipeVersion": recipe_version,
            "caseId": case_id,
            "status": "running",
            "currentStepId": None,
            "projectId": None,
            "batchId": None,
            "runtime": runtime,
            "startedAt": now_iso(),
            "updatedAt": now_iso(),
            "finishedAt": None,
            "steps": [],
            "toolCalls": [],
            "approvals": [],
            "errors": [],
            "providerCalls": {"fish": 0, "paidImage": 0, "paidVideo": 0},
            "cost": {"currency": "USD", "amount": 0},
        }
        run_dir = self.run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=False)
        atomic_write_json(run_dir / "run.json", data)
        atomic_write_json(run_dir / "decisions.json", {"approvals": []})
        atomic_write_json(run_dir / "artifacts.json", {})
        atomic_write_json(run_dir / "eval.json", {})
        (run_dir / "events.jsonl").write_text("", encoding="utf-8")
        return data

    def load(self, run_id: str) -> dict[str, Any]:
        return json.loads((self.run_dir(run_id) / "run.json").read_text(encoding="utf-8"))

    def list(self) -> list[dict[str, Any]]:
        runs = []
        for directory in self.root.iterdir():
            path = directory / "run.json"
            if not path.is_file():
                continue
            try:
                runs.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return sorted(runs, key=lambda run: str(run.get("updatedAt") or run.get("startedAt") or ""), reverse=True)

    def save(self, run: dict[str, Any]) -> None:
        run["updatedAt"] = now_iso()
        atomic_write_json(self.run_dir(run["runId"]) / "run.json", run)

    def events(self, run_id: str, after: int = 0) -> list[dict[str, Any]]:
        path = self.run_dir(run_id) / "events.jsonl"
        if not path.is_file():
            raise FileNotFoundError(run_id)
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if int(payload.get("sequence") or 0) > after:
                events.append(payload)
        return events

    def append_event(self, run_id: str, event: dict[str, Any]) -> dict[str, Any]:
        path = self.run_dir(run_id) / "events.jsonl"
        prior = self.events(run_id)
        sequence = int(prior[-1].get("sequence") or 0) + 1 if prior else 1
        record = sanitize({"sequence": sequence, "time": now_iso(), **event})
        payload = json.dumps(record, ensure_ascii=False)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
            handle.flush()
        return record

    def save_eval(self, run_id: str, data: dict[str, Any]) -> None:
        atomic_write_json(self.run_dir(run_id) / "eval.json", data)

    def load_decisions(self, run_id: str) -> dict[str, Any]:
        path = self.run_dir(run_id) / "decisions.json"
        if not path.exists():
            return {"approvals": []}
        return json.loads(path.read_text(encoding="utf-8"))

    def save_decisions(self, run_id: str, data: dict[str, Any]) -> None:
        atomic_write_json(self.run_dir(run_id) / "decisions.json", data)
