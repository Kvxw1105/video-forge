from __future__ import annotations

import json
import os
import subprocess
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4


class PiRpcError(RuntimeError):
    """Raised when the Pi RPC sidecar cannot complete a JSONL request."""


def normalize_pi_event(event: dict[str, Any]) -> dict[str, Any]:
    """Map Pi's stable session events to Director timeline event names."""
    event_type = str(event.get("type") or "pi.event")
    mapping = {
        "turn_start": "agent.turn.started",
        "agent_settled": "agent.settled",
        "agent_end": "agent.turn.ended",
        "tool_execution_start": "tool.call.started",
        "tool_execution_update": "tool.call.updated",
        "tool_execution_end": "tool.call.failed" if event.get("isError") else "tool.call.succeeded",
        "message_update": "agent.message.updated",
        "extension_error": "pi.extension.error",
    }
    normalized = {"type": mapping.get(event_type, "pi.event"), "piEventType": event_type, "piEvent": event}
    if event_type.startswith("tool_execution_"):
        normalized.update({key: event.get(key) for key in ("toolCallId", "toolName", "args", "result", "isError") if key in event})
    if event_type == "message_update":
        assistant_event = event.get("assistantMessageEvent") or {}
        normalized["delta"] = assistant_event.get("delta") or assistant_event.get("text") or ""
    return normalized


class _PiRpcSidecar:
    """A single Pi RPC process with strict JSONL request correlation."""

    def __init__(self, command: Sequence[str], *, cwd: Path, on_event: Callable[[dict[str, Any]], None]):
        self._command = list(command)
        self._cwd = cwd
        self._on_event = on_event
        self._pending: dict[str, tuple[threading.Event, dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._closed = False
        self._stderr: list[str] = []
        self._process = subprocess.Popen(
            self._command,
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    def request(self, command: dict[str, Any], *, timeout: float = 15.0) -> dict[str, Any]:
        if self._closed:
            raise PiRpcError("Pi RPC sidecar is closed")
        if self._process.poll() is not None:
            raise PiRpcError(self._exit_message())
        request_id = f"vf_{uuid4().hex}"
        response: dict[str, Any] = {}
        ready = threading.Event()
        with self._lock:
            self._pending[request_id] = (ready, response)
            try:
                assert self._process.stdin is not None
                self._process.stdin.write(json.dumps({**command, "id": request_id}, ensure_ascii=False) + "\n")
                self._process.stdin.flush()
            except (OSError, ValueError) as exc:
                self._pending.pop(request_id, None)
                raise PiRpcError(f"Could not write Pi RPC command {command.get('type')}: {exc}") from exc
        if not ready.wait(timeout):
            with self._lock:
                self._pending.pop(request_id, None)
            raise PiRpcError(f"Timed out waiting for Pi RPC command {command.get('type')}. {self._stderr_tail()}")
        if not response.get("success"):
            raise PiRpcError(str(response.get("error") or f"Pi RPC command {command.get('type')} failed"))
        return response

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2)
        self._reject_pending(self._exit_message())

    def _read_stdout(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                self._on_event({"type": "pi.rpc.protocol_error", "message": "Pi emitted invalid JSONL"})
                continue
            request_id = payload.get("id")
            if payload.get("type") == "response" and isinstance(request_id, str):
                with self._lock:
                    pending = self._pending.pop(request_id, None)
                if pending:
                    ready, response = pending
                    response.update(payload)
                    ready.set()
                    continue
            self._on_event(payload)
        self._reject_pending(self._exit_message())

    def _read_stderr(self) -> None:
        assert self._process.stderr is not None
        for line in self._process.stderr:
            self._stderr.append(line.rstrip())
            del self._stderr[:-20]

    def _reject_pending(self, message: str) -> None:
        with self._lock:
            pending = list(self._pending.values())
            self._pending.clear()
        for ready, response in pending:
            response.update({"success": False, "error": message})
            ready.set()

    def _stderr_tail(self) -> str:
        return " ".join(self._stderr[-5:])

    def _exit_message(self) -> str:
        return f"Pi RPC sidecar exited with code {self._process.poll()}. {self._stderr_tail()}".strip()


class PiRpcTransport:
    """VideoForge-owned adapter for Pi's existing RPC sidecar protocol.

    Pi owns its agent/session loop. VideoForge owns RunStore, project data, and
    delivery artifacts. The sidecar starts with all Pi built-in tools disabled;
    only explicitly supplied VideoForge extensions may be enabled later.
    """

    name = "pi_rpc"

    def __init__(self, command: Sequence[str], *, cwd: Path, run_dir: Callable[[str], Path], event_sink: Callable[[str, dict[str, Any]], None] | None = None):
        if not command:
            raise ValueError("Pi RPC command is required")
        self._command = tuple(command)
        self._cwd = cwd
        self._run_dir = run_dir
        self._event_sink = event_sink
        self._sidecars: dict[str, _PiRpcSidecar] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_environment(cls, *, run_dir: Callable[[str], Path], repo_root: Path, event_sink: Callable[[str, dict[str, Any]], None] | None = None) -> PiRpcTransport:
        raw_command = os.getenv("VIDEOFORGE_PI_RPC_COMMAND", "").strip()
        if raw_command:
            try:
                command = json.loads(raw_command)
            except json.JSONDecodeError as exc:
                raise ValueError("VIDEOFORGE_PI_RPC_COMMAND must be a JSON array") from exc
            if not isinstance(command, list) or not all(isinstance(part, str) and part for part in command):
                raise ValueError("VIDEOFORGE_PI_RPC_COMMAND must be a non-empty JSON string array")
        else:
            source = Path(os.getenv("VIDEOFORGE_PI_SOURCE", "")).expanduser()
            entry = source / "packages" / "coding-agent" / "dist" / "rpc-entry.js"
            if not source or not entry.is_file():
                raise ValueError("Set VIDEOFORGE_PI_SOURCE to a built Pi checkout or VIDEOFORGE_PI_RPC_COMMAND to a JSON command array")
            model = os.getenv("VIDEOFORGE_PI_MODEL", "openai/gpt-4o-mini")
            extension = repo_root / "backend" / "agent_runtime" / "pi_extensions" / "recipe_contract.mjs"
            command = [
                "node", str(entry), "--mode", "rpc", "--model", model,
                "--no-builtin-tools", "--no-extensions", "--extension", str(extension),
                "--tools", "videoforge_recipe_contract", "--no-skills", "--no-prompt-templates", "--no-context-files",
            ]
        return cls(command, cwd=repo_root, run_dir=run_dir, event_sink=event_sink)

    def create_session(self, run_id: str, task: str) -> dict[str, Any]:
        sidecar = self._get_or_start(run_id)
        response = sidecar.request({"type": "get_state"})
        state = response.get("data") or {}
        return {
            "sessionId": state.get("sessionId"),
            "sessionFile": state.get("sessionFile"),
            "mockTransport": False,
            "liveCallPerformed": False,
            "networkCalls": None,
            "task": task,
        }

    def initial_events(self, run_id: str, task: str) -> list[dict[str, Any]]:
        with self._lock:
            streamed = self._events.pop(run_id, [])
        return [
            {"type": "pi.sidecar.ready", "runId": run_id, "transport": self.name, "taskQueued": False},
            {"type": "pi.session.created", "runId": run_id, "transport": self.name},
            *([] if self._event_sink else streamed),
        ]

    def set_event_sink(self, event_sink: Callable[[str, dict[str, Any]], None] | None) -> None:
        self._event_sink = event_sink

    def follow_up(self, run_id: str, message: str) -> None:
        self._get_or_start(run_id).request({"type": "follow_up", "message": message})

    def prompt(self, run_id: str, message: str) -> dict[str, Any]:
        self._get_or_start(run_id).request({"type": "prompt", "message": message})
        return {"accepted": True, "settled": False}

    def abort(self, run_id: str) -> None:
        sidecar = self._sidecars.get(run_id)
        if sidecar:
            sidecar.request({"type": "abort"}, timeout=5)

    def shutdown(self, run_id: str) -> None:
        with self._lock:
            sidecar = self._sidecars.pop(run_id, None)
        if sidecar:
            sidecar.close()

    def _get_or_start(self, run_id: str) -> _PiRpcSidecar:
        with self._lock:
            current = self._sidecars.get(run_id)
            if current:
                return current
            session_dir = self._run_dir(run_id) / "pi-session"
            session_dir.mkdir(parents=True, exist_ok=True)
            command = [*self._command, "--session-dir", str(session_dir)]
            sidecar = _PiRpcSidecar(command, cwd=self._cwd, on_event=lambda event: self._record_event(run_id, event))
            self._sidecars[run_id] = sidecar
            return sidecar

    def _record_event(self, run_id: str, event: dict[str, Any]) -> None:
        normalized = normalize_pi_event(event)
        if self._event_sink:
            self._event_sink(run_id, normalized)
        with self._lock:
            self._events.setdefault(run_id, []).append(normalized)


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

    def prompt(self, run_id: str, message: str) -> dict[str, Any]:
        return {"accepted": True, "settled": True}
