import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import create_app
from models.system_readiness import ReadinessCheck
from services import system_readiness as readiness


def _patch_common(monkeypatch, tmp_path):
    projects = tmp_path / "projects"
    library = tmp_path / "library"
    temp = tmp_path / "temp"
    projects.mkdir()
    library.mkdir()
    monkeypatch.setattr(readiness, "PROJECTS_DIR", projects)
    monkeypatch.setattr(readiness, "LIBRARY_DIR", library)
    monkeypatch.setattr(readiness, "TEMP_DIR", temp)
    monkeypatch.setattr(readiness, "JIANYING_DRAFT_DIR", None)
    monkeypatch.setattr(readiness, "shutil_which", lambda name: None)
    monkeypatch.setattr(readiness, "resolve_frontend_dist", lambda: tmp_path / "missing-dist")
    monkeypatch.setattr(readiness, "get_tts_settings_raw", lambda: readiness.TtsSettings(engine="edge"))


def test_readiness_aggregation_states():
    assert readiness.aggregate_status([ReadinessCheck(id="a", label="a", status="pass", required=True, message="ok")]) == "ready"
    assert readiness.aggregate_status([ReadinessCheck(id="a", label="a", status="warn", required=False, message="warn")]) == "degraded"
    assert readiness.aggregate_status([ReadinessCheck(id="a", label="a", status="fail", required=True, message="bad")]) == "blocked"


def test_storage_probe_writes_and_cleans_probe_file(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    check = readiness.check_writable_directory(tmp_path / "probe", "storage.projects", "Projects", True)
    assert check.status == "pass"
    assert not list((tmp_path / "probe").glob(".videoforge-readiness-*"))


def test_disk_thresholds(monkeypatch):
    monkeypatch.setattr(readiness.shutil, "disk_usage", lambda path: type("U", (), {"total": 10 * 1024**3, "used": 6 * 1024**3, "free": 4 * 1024**3})())
    check = readiness.check_disk()
    assert check.status == "warn"
    assert check.details["freeBytes"] == 4 * 1024**3
    assert check.details["freeGb"] == pytest.approx(4.0)


def test_ffmpeg_missing_is_warning_without_shell(monkeypatch):
    monkeypatch.setattr(readiness, "shutil_which", lambda name: None)
    check = readiness.check_ffmpeg()
    assert check.status == "warn"
    assert check.required is False


def test_ffmpeg_version_is_pass(monkeypatch):
    monkeypatch.setattr(readiness, "shutil_which", lambda name: "ffmpeg.exe")
    calls = []
    monkeypatch.setattr(readiness.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)) or type("R", (), {"returncode": 0, "stdout": "ffmpeg version 7.0\n", "stderr": ""})())
    check = readiness.check_ffmpeg()
    assert check.status == "pass"
    assert check.details["version"] == "ffmpeg version 7.0"
    assert calls[0][0][0] == ["ffmpeg.exe", "-version"]
    assert calls[0][1]["shell"] is False


def test_ffmpeg_timeout_is_controlled_warning(monkeypatch):
    monkeypatch.setattr(readiness, "shutil_which", lambda name: "ffmpeg")
    def timeout(*args, **kwargs):
        raise readiness.subprocess.TimeoutExpired(["ffmpeg", "-version"], 3)
    monkeypatch.setattr(readiness.subprocess, "run", timeout)
    check = readiness.check_ffmpeg()
    assert check.status == "warn"
    assert check.details["error"] == "timeout"


def test_ffmpeg_nonzero_is_controlled_failure(monkeypatch):
    monkeypatch.setattr(readiness, "shutil_which", lambda name: "ffmpeg")
    monkeypatch.setattr(readiness.subprocess, "run", lambda *args, **kwargs: type("R", (), {"returncode": 1, "stdout": "", "stderr": "bad"})())
    check = readiness.check_ffmpeg()
    assert check.status == "fail"
    assert check.details["error"] == "non-zero exit"


def test_tts_edge_does_not_expose_secrets(monkeypatch):
    monkeypatch.setattr(readiness, "get_tts_settings_raw", lambda: readiness.TtsSettings(engine="edge", fishApiKey="secret"))
    check = readiness.check_tts()
    assert check.status == "pass"
    assert "secret" not in json.dumps(check.model_dump())
    assert check.details["selectedEngine"] == "edge"


def test_tts_fish_missing_reference_warns_without_key(monkeypatch):
    monkeypatch.setattr(readiness, "get_tts_settings_raw", lambda: readiness.TtsSettings(engine="fish", fishApiKey="secret", fishReferenceId=""))
    check = readiness.check_tts()
    assert check.status == "warn"
    assert check.details["missingFields"] == ["fishReferenceId"]
    assert "secret" not in json.dumps(check.model_dump())


def test_jianying_missing_is_warning_and_zip_remains_available(monkeypatch):
    monkeypatch.setattr(readiness, "JIANYING_DRAFT_DIR", None)
    check = readiness.check_jianying()
    assert check.status == "warn"
    checks = [ReadinessCheck(id=item, label=item, status="pass", required=True, message="ok") for item in ("storage.projects", "storage.library", "storage.temp")]
    result = readiness.build_capabilities(checks, check, True)
    assert result["jianyingZipExport"] is True
    assert result["jianyingDirectExport"] is False


def test_jianying_detected_counts_only_draft_content_directories(monkeypatch, tmp_path):
    root = tmp_path / "drafts"
    (root / "one").mkdir(parents=True)
    (root / "one" / "draft_content.json").write_text("{}")
    (root / "incomplete").mkdir()
    monkeypatch.setattr(readiness, "JIANYING_DRAFT_DIR", root)
    check = readiness.check_jianying()
    assert check.status == "pass"
    assert check.details["draftCount"] == 1
    assert check.details["draftDirectory"] == str(root.resolve())


def test_frontend_required_depends_on_production(monkeypatch, tmp_path):
    monkeypatch.setattr(readiness, "resolve_frontend_dist", lambda: tmp_path / "missing")
    assert readiness.check_frontend(production_mode=False).status == "warn"
    assert readiness.check_frontend(production_mode=True).status == "fail"


def test_frontend_complete_build_is_pass(monkeypatch, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>")
    (dist / "assets" / "app.js").write_text("ok")
    monkeypatch.setattr(readiness, "resolve_frontend_dist", lambda: dist)
    check = readiness.check_frontend(production_mode=True)
    assert check.status == "pass"
    assert check.details["path"] == str(dist)


def test_readiness_response_is_cached_and_refreshes(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    calls = {"count": 0}
    original = readiness.run_checks
    def wrapped(*args, **kwargs):
        calls["count"] += 1
        return original(*args, **kwargs)
    monkeypatch.setattr(readiness, "run_checks", wrapped)
    readiness.clear_cache()
    client = TestClient(create_app())
    first = client.get("/api/system/readiness")
    second = client.get("/api/system/readiness")
    refreshed = client.get("/api/system/readiness?refresh=true")
    assert first.status_code == second.status_code == refreshed.status_code == 200
    assert calls["count"] == 2
    assert first.json().keys() >= {"status", "checkedAt", "app", "checks", "capabilities", "summary"}


def test_readiness_never_serializes_secret_or_traceback(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(readiness, "get_tts_settings_raw", lambda: readiness.TtsSettings(engine="fish", fishApiKey="super-secret", fishReferenceId=""))
    readiness.clear_cache()
    response = TestClient(create_app()).get("/api/system/readiness?refresh=true")
    body = response.text
    assert response.status_code == 200
    assert "super-secret" not in body
    assert "Traceback" not in body
    assert "Authorization" not in body


def test_readiness_check_schema_has_required_fields(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    readiness.clear_cache()
    body = TestClient(create_app()).get("/api/system/readiness?refresh=true").json()
    assert body["status"] in {"ready", "degraded", "blocked"}
    assert body["app"]["name"] == "VideoForge"
    assert set(body["capabilities"]) == {"projectEditing", "voiceover", "previewRendering", "jianyingZipExport", "jianyingDirectExport"}
    assert body["summary"]["passed"] + body["summary"]["warnings"] + body["summary"]["failed"] == len(body["checks"])
    for item in body["checks"]:
        assert set(item) >= {"id", "label", "status", "required", "message", "details"}


def test_single_check_exception_is_reported_without_api_500(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(readiness, "check_ffmpeg", lambda: (_ for _ in ()).throw(RuntimeError("unexpected")))
    readiness.clear_cache()
    response = TestClient(create_app()).get("/api/system/readiness?refresh=true")
    assert response.status_code == 200
    ffmpeg = next(item for item in response.json()["checks"] if item["id"] == "runtime.ffmpeg")
    assert ffmpeg["status"] == "warn"
    assert ffmpeg["details"]["error"] == "RuntimeError"


def test_readiness_health_regression():
    client = TestClient(create_app())
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/projects").status_code == 200
