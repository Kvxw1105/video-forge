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


def test_tts_fish_audio_missing_reference_warns_without_key(monkeypatch):
    monkeypatch.setattr(readiness, "get_tts_settings_raw", lambda: readiness.TtsSettings(engine="fish_audio", fishApiKey="secret", fishReferenceId=""))
    check = readiness.check_tts()
    assert check.status == "warn"
    assert check.details["missingFields"] == ["fishReferenceId"]
    assert "secret" not in json.dumps(check.model_dump())


@pytest.mark.parametrize("settings, expected", [
    (dict(engine="fish_audio", fishApiKey="key", fishReferenceId="ref"), ("pass", True, False)),
    (dict(engine="fish_audio", fishApiKey="", fishReferenceId="ref"), ("warn", False, False)),
    (dict(engine="fish_audio", fishApiKey="key", fishReferenceId=""), ("warn", False, False)),
    (dict(engine="manbo", manboApiKey="key", manboApiUrl="https://example.test/tts"), ("pass", True, False)),
    (dict(engine="manbo", manboApiKey=""), ("warn", False, False)),
    (dict(engine="custom", customApiUrl="https://example.test/tts", customApiKey=""), ("pass", True, True)),
    (dict(engine="custom", customApiUrl="", customApiKey="key"), ("warn", False, True)),
    (dict(engine="none"), ("pass", False, True)),
    (dict(engine="fish"), ("warn", False, False)),
])
def test_tts_engine_semantics(monkeypatch, settings, expected):
    monkeypatch.setattr(readiness, "get_tts_settings_raw", lambda: readiness.TtsSettings(**settings))
    check = readiness.check_tts()
    assert (check.status, check.details["voiceoverAvailable"], check.details["availableWithoutExternalKey"]) == expected
    assert "key" not in json.dumps(check.model_dump())
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


def test_jianying_probe_writes_and_cleans_only_probe_file(monkeypatch, tmp_path):
    root = tmp_path / "drafts"
    root.mkdir()
    monkeypatch.setattr(readiness, "JIANYING_DRAFT_DIR", root)
    monkeypatch.setattr(readiness.os, "access", lambda path, mode: True)
    check = readiness.check_jianying()
    assert check.status == "pass"
    assert not list(root.glob(".videoforge-readiness-*"))
    assert not (root / "draft_content.json").exists()


def test_jianying_probe_success_overrides_false_os_access(monkeypatch, tmp_path):
    root = tmp_path / "drafts"
    root.mkdir()
    monkeypatch.setattr(readiness, "JIANYING_DRAFT_DIR", root)
    monkeypatch.setattr(readiness.os, "access", lambda path, mode: False)
    check = readiness.check_jianying()
    assert check.status == "pass"
    assert check.details["writable"] is True
    assert readiness.build_capabilities([
        ReadinessCheck(id="storage.projects", label="p", status="pass", required=True, message="ok"),
        ReadinessCheck(id="storage.library", label="l", status="pass", required=True, message="ok"),
        ReadinessCheck(id="storage.temp", label="t", status="pass", required=True, message="ok"),
    ], check)["jianyingDirectExport"] is True


def test_jianying_probe_failure_overrides_true_os_access(monkeypatch, tmp_path):
    root = tmp_path / "drafts"
    root.mkdir()
    monkeypatch.setattr(readiness, "JIANYING_DRAFT_DIR", root)
    monkeypatch.setattr(readiness.os, "access", lambda path, mode: True)
    monkeypatch.setattr(readiness, "check_writable_directory", lambda *args: ReadinessCheck(
        id="integration.jianying", label="j", status="fail", required=False,
        message="failed", details={"path": str(root), "error": "write_failed"},
    ))
    check = readiness.check_jianying()
    assert check.status == "fail"
    assert check.details["writable"] is False
    assert check.details["error"] == "write_failed"


def test_jianying_status_route_preserves_legacy_shape(monkeypatch, tmp_path):
    from routers import export
    root = tmp_path / "drafts"
    (root / "draft-one").mkdir(parents=True)
    (root / "draft-one" / "draft_content.json").write_text("{}")
    monkeypatch.setattr(export, "JIANYING_DRAFT_DIR", root)
    body = TestClient(create_app()).get("/api/jianying-status").json()
    assert set(body) == {"detected", "path", "drafts"}
    assert body["detected"] is True
    assert body["drafts"] == [{"name": "draft-one", "folder": "draft-one"}]


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


def test_readiness_uses_app_frontend_dist_override(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    dist = tmp_path / "custom-dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>")
    (dist / "assets" / "app.js").write_text("ok")
    readiness.clear_cache()
    app = create_app(serve_frontend=True, frontend_dist=dist)
    body = TestClient(app).get("/api/system/readiness?refresh=true").json()
    frontend = next(item for item in body["checks"] if item["id"] == "runtime.frontend")
    assert frontend["status"] == "pass"
    assert Path(frontend["details"]["path"]) == dist.resolve()


def test_readiness_cache_isolated_by_frontend_dist(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    dist_a = tmp_path / "a"; (dist_a / "assets").mkdir(parents=True); (dist_a / "index.html").write_text("a"); (dist_a / "assets" / "a.js").write_text("a")
    dist_b = tmp_path / "b"; (dist_b / "assets").mkdir(parents=True); (dist_b / "index.html").write_text("b"); (dist_b / "assets" / "b.js").write_text("b")
    readiness.clear_cache()
    a = TestClient(create_app(serve_frontend=True, frontend_dist=dist_a)).get("/api/system/readiness").json()
    b = TestClient(create_app(serve_frontend=True, frontend_dist=dist_b)).get("/api/system/readiness").json()
    assert next(item for item in a["checks"] if item["id"] == "runtime.frontend")["details"]["path"] != next(item for item in b["checks"] if item["id"] == "runtime.frontend")["details"]["path"]


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


def test_writable_probe_cleans_after_fsync_failure(monkeypatch, tmp_path):
    def fail_fsync(fd):
        raise OSError("fsync failed")
    monkeypatch.setattr(readiness.os, "fsync", fail_fsync)
    check = readiness.check_writable_directory(tmp_path / "probe", "storage.projects", "Projects", True)
    assert check.status == "fail"
    assert not list((tmp_path / "probe").glob(".videoforge-readiness-*"))


def test_disk_is_always_required(monkeypatch):
    monkeypatch.setattr(readiness.shutil, "disk_usage", lambda path: type("U", (), {"total": 10, "used": 9, "free": 0})())
    check = readiness.check_disk()
    assert check.required is True


def test_disk_usage_exception_is_required_and_degraded(monkeypatch):
    monkeypatch.setattr(readiness.shutil, "disk_usage", lambda path: (_ for _ in ()).throw(OSError("disk unavailable")))
    check = readiness.check_disk()
    assert check.status == "warn"
    assert check.required is True
    assert readiness.aggregate_status([check]) == "degraded"


def test_disk_below_one_gb_is_required_and_blocked(monkeypatch):
    monkeypatch.setattr(readiness.shutil, "disk_usage", lambda path: type("U", (), {"total": 10, "used": 9, "free": 1024**3 - 1})())
    check = readiness.check_disk()
    assert check.status == "fail"
    assert check.required is True
    assert readiness.aggregate_status([check]) == "blocked"


def test_manbo_missing_url_is_reported(monkeypatch):
    monkeypatch.setattr(readiness, "get_tts_settings_raw", lambda: readiness.TtsSettings(engine="manbo", manboApiKey="key", manboApiUrl=""))
    check = readiness.check_tts()
    assert check.details["missingFields"] == ["manboApiUrl"]


def test_manbo_missing_key_and_url_is_reported_in_stable_order(monkeypatch):
    monkeypatch.setattr(readiness, "get_tts_settings_raw", lambda: readiness.TtsSettings(engine="manbo", manboApiKey="", manboApiUrl=""))
    check = readiness.check_tts()
    assert check.details["missingFields"] == ["manboApiKey", "manboApiUrl"]


def test_none_mode_has_subtitles_only_message(monkeypatch):
    monkeypatch.setattr(readiness, "get_tts_settings_raw", lambda: readiness.TtsSettings(engine="none"))
    check = readiness.check_tts()
    assert check.status == "pass"
    assert check.message == "已启用纯字幕模式"
    assert check.details["mode"] == "subtitles_only"
    assert check.details["voiceoverAvailable"] is False


def test_probe_cleanup_retries_once_then_succeeds(monkeypatch, tmp_path):
    target = tmp_path / "probe"
    calls = {"count": 0}
    original_unlink = Path.unlink
    def flaky_unlink(path, *args, **kwargs):
        if path.parent == target and path.name.startswith(".videoforge-readiness-"):
            calls["count"] += 1
            if calls["count"] == 1:
                raise OSError("busy")
        return original_unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", flaky_unlink)
    monkeypatch.setattr(readiness.time, "sleep", lambda seconds: None)
    check = readiness.check_writable_directory(target, "storage.temp", "Temp", True)
    assert check.status == "pass"
    assert calls["count"] == 2


def test_probe_cleanup_failure_is_not_silent_pass(monkeypatch, tmp_path):
    target = tmp_path / "probe"
    def always_fail_unlink(path, *args, **kwargs):
        if path.parent == target and path.name.startswith(".videoforge-readiness-"):
            raise OSError("locked")
        return Path.unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", always_fail_unlink)
    monkeypatch.setattr(readiness.time, "sleep", lambda seconds: None)
    check = readiness.check_writable_directory(target, "storage.temp", "Temp", True)
    assert check.status == "fail"
    assert check.details["error"] == "cleanup_failed"
    assert check.details["errorType"] == "OSError"


def test_cache_timestamp_is_recorded_after_checks(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    readiness.clear_cache()
    ticks = iter([100.0, 150.0])
    monkeypatch.setattr(readiness.time, "monotonic", lambda: next(ticks))
    readiness.get_readiness(refresh=True)
    assert readiness._cache[0] == 150.0


def test_readiness_user_labels_and_messages_are_chinese(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    readiness.clear_cache()
    body = TestClient(create_app()).get("/api/system/readiness?refresh=true").json()
    text = json.dumps([(item["label"], item["message"]) for item in body["checks"]], ensure_ascii=False)
    for forbidden in ("writable", "cleanup failed", "Disk space", "JianYing draft directory"):
        assert forbidden not in text
    for item_id, expected_label in (("storage.projects", "项目目录"), ("storage.library", "素材库目录"), ("storage.temp", "临时目录"), ("storage.disk", "磁盘空间"), ("integration.jianying", "剪映草稿目录")):
        item = next(item for item in body["checks"] if item["id"] == item_id)
        assert item["label"] == expected_label


def test_storage_success_messages_end_with_ke_xie(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    checks = [readiness.check_writable_directory(path, item_id, label, True) for path, item_id, label in (
        (tmp_path / "projects", "storage.projects", "项目目录"),
        (tmp_path / "library", "storage.library", "素材库目录"),
        (tmp_path / "temp", "storage.temp", "临时目录"),
    )]
    assert all(item.status == "pass" and item.message.endswith("可写") for item in checks)


def test_disk_and_jianying_labels_are_stable(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(readiness.shutil, "disk_usage", lambda path: type("U", (), {"total": 10 * 1024**3, "used": 1 * 1024**3, "free": 9 * 1024**3})())
    assert readiness.check_disk().label == "磁盘空间"
    assert readiness.check_jianying().label == "剪映草稿目录"


def test_check_tts_reads_settings_once(monkeypatch):
    calls = {"count": 0}
    def load_once():
        calls["count"] += 1
        return readiness.TtsSettings(engine="manbo", manboApiKey="key", manboApiUrl="https://example.test")
    monkeypatch.setattr(readiness, "get_tts_settings_raw", load_once)
    assert readiness.check_tts().status == "pass"
    assert calls["count"] == 1


def test_readiness_health_regression():
    client = TestClient(create_app())
    health = client.get("/api/health")
    readiness.clear_cache()
    system = client.get("/api/system/readiness?refresh=true")
    assert health.status_code == 200
    assert system.status_code == 200
    assert health.json()["version"] == system.json()["app"]["version"]
    runtime = next(item for item in system.json()["checks"] if item["id"] == "app.runtime")
    assert runtime["details"]["version"] == system.json()["app"]["version"]
    assert client.get("/api/projects").status_code == 200
