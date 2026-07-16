import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import process_utils


def test_run_hides_console_window_on_windows(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return "completed"

    monkeypatch.setattr(process_utils.os, "name", "nt")
    monkeypatch.setattr(process_utils.subprocess, "run", fake_run)

    result = process_utils.run(["ffprobe", "-version"])

    assert result == "completed"
    assert calls[0][1]["creationflags"] == subprocess.CREATE_NO_WINDOW
    assert calls[0][1]["encoding"] == "utf-8"
    assert calls[0][1]["errors"] == "replace"
