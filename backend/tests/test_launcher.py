import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import launcher


def test_select_port_skips_busy_default_ports(monkeypatch):
    monkeypatch.setattr(launcher, "is_port_available", lambda port: port == 8767)
    assert launcher.select_port(None) == 8767


def test_explicit_busy_port_fails_without_fallback(monkeypatch):
    monkeypatch.setattr(launcher, "is_port_available", lambda port: False)
    with pytest.raises(RuntimeError, match="Port 9000 is unavailable"):
        launcher.select_port(9000)


def test_validate_frontend_dist_reports_repair_command(tmp_path):
    with pytest.raises(RuntimeError, match="npm run build"):
        launcher.validate_frontend_dist(tmp_path / "dist")


def test_no_browser_flag_does_not_open_browser(monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr(launcher, "validate_frontend_dist", lambda path: tmp_path)
    monkeypatch.setattr(launcher, "select_port", lambda requested: 8765)
    monkeypatch.setattr(launcher, "create_app", lambda **kwargs: object())
    monkeypatch.setattr(launcher.uvicorn, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: opened.append(url))

    assert launcher.run(["--no-browser"]) == 0
    assert opened == []
